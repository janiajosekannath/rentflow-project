from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from mysql.connector.pooling import MySQLConnectionPool
import mysql.connector
import threading
import time

# ─────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 30
})

# ─────────────────────────────────────────────
#  DATABASE POOL (replaces slow per-request connect)
# ─────────────────────────────────────────────
DB_CONFIG = {
    'host':     'maglev.proxy.rlwy.net',
    'port':     50013,
    'user':     'root',
    'password': 'qaWhtljpmFJDWNUIFZlSyxdvFweRSvSd',
    'database': 'rentflow_db',
    'charset':  'utf8mb4',
}

pool = MySQLConnectionPool(
    pool_name="rentflow",
    pool_size=10,
    connection_timeout=30,
    **DB_CONFIG
)

def get_db():
    for attempt in range(3):
        try:
            conn = pool.get_connection()
            cur  = conn.cursor(dictionary=True)
            return conn, cur
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                raise e

# ─────────────────────────────────────────────
#  KEEP-ALIVE (prevents Railway cold starts)
# ─────────────────────────────────────────────
def keep_alive():
    time.sleep(60)  # wait for app to fully start
    while True:
        try:
            conn, cur = get_db()
            cur.execute("SELECT 1")
            cur.close(); conn.close()
        except:
            pass
        time.sleep(300)  # ping every 5 minutes

threading.Thread(target=keep_alive, daemon=True).start()

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def ok(data=None, msg="success"):
    return jsonify({"status": "ok", "message": msg, "data": data})

def err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code

def dates_to_str(rows, keys):
    for r in rows:
        for k in keys:
            if r.get(k): r[k] = str(r[k])
    return rows

# ─────────────────────────────────────────────
#  STATIC / HEALTH
# ─────────────────────────────────────────────
@app.route("/frontend/<path:filename>")
def frontend(filename):
    return send_from_directory("../frontend", filename)

@app.route("/")
def home():
    return "RentFlow Backend Running ✅"

@app.route("/health")
def health():
    return {"status": "ok"}, 200

# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────
@app.route("/login", methods=["POST"])
def login():
    d        = request.json
    email    = d.get("email", "").strip()
    password = d.get("password", "")
    role     = d.get("role", "")

    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT * FROM admins WHERE email=%s AND password=%s AND role=%s
        """, (email, password, role))
        user = cur.fetchone()

        if user:
            user_data = {
                "id":    user["id"],
                "name":  user["name"],
                "email": user["email"],
                "role":  user["role"],
            }
            if user["role"] == "client":
                cur.execute("""
                    SELECT phone, address, id_proof_type, id_proof_number, created_at
                    FROM customers WHERE email=%s LIMIT 1
                """, (email,))
                customer = cur.fetchone()
                if customer:
                    user_data["phone"]           = customer["phone"]
                    user_data["address"]         = customer["address"]
                    user_data["id_proof_type"]   = customer["id_proof_type"]
                    user_data["id_proof_number"] = customer["id_proof_number"]
                    user_data["created_at"]      = str(customer["created_at"]) if customer["created_at"] else None
            return ok(user_data, "Login successful")
        else:
            return err("Invalid email, password, or role", 401)
    finally:
        cur.close(); conn.close()

@app.route("/register", methods=["POST"])
def register():
    d = request.json
    conn, cur = get_db()
    try:
        cur.execute("""
            INSERT INTO admins (name, email, password, role)
            VALUES (%s, %s, %s, 'client')
        """, (d["name"], d["email"], d["password"]))

        cur.execute("""
            INSERT IGNORE INTO customers (name, phone, email)
            VALUES (%s, %s, %s)
        """, (d["name"], d.get("phone", ""), d["email"]))

        conn.commit()
        return ok({"id": cur.lastrowid}, "Account created successfully")
    except mysql.connector.IntegrityError:
        return err("Email already registered")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  DASHBOARD (cached 20s — runs many queries)
# ─────────────────────────────────────────────
@app.route("/dashboard")
@cache.cached(timeout=20)
def dashboard():
    conn, cur = get_db()
    try:
        # Batch counts in one query
        cur.execute("""
            SELECT
                COUNT(*) AS total_equipment,
                SUM(status='Available') AS available_equipment
            FROM equipment
        """)
        eq = cur.fetchone()

        cur.execute("""
            SELECT
                SUM(status='Active')  AS active_rentals,
                SUM(status='Overdue') AS overdue_rentals
            FROM rentals
        """)
        rn = cur.fetchone()

        # Auto-update overdue in background (non-blocking)
        cur.execute("""
            UPDATE rentals SET status='Overdue'
            WHERE status='Active'
              AND expected_return_date < CURDATE()
              AND actual_return_date IS NULL
        """)
        conn.commit()

        cur.execute("""
            SELECT c.name AS customer, e.name AS equipment,
                   r.status, r.expected_return_date
            FROM rentals r
            JOIN customers c ON r.customer_id = c.id
            JOIN equipment  e ON r.equipment_id = e.id
            ORDER BY r.id DESC LIMIT 5
        """)
        recent_rentals = cur.fetchall()
        dates_to_str(recent_rentals, ["expected_return_date"])

        cur.execute("""
            SELECT c.name, 'Deposit Refund' AS type, d.amount_paid AS amount
            FROM deposits d
            JOIN rentals r  ON d.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            WHERE d.refund_status = 'Pending'
            UNION ALL
            SELECT c.name, 'Late Fee', lf.total_fee
            FROM late_fees lf
            JOIN rentals r  ON lf.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            WHERE lf.payment_status = 'Unpaid'
            LIMIT 6
        """)
        pending = cur.fetchall()

        return ok({
            "total_equipment":     eq["total_equipment"],
            "available_equipment": eq["available_equipment"],
            "active_rentals":      rn["active_rentals"],
            "overdue_rentals":     rn["overdue_rentals"],
            "recent_rentals":      recent_rentals,
            "pending_items":       pending
        })
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  CUSTOMERS
# ─────────────────────────────────────────────
@app.route("/customers")
@cache.cached(timeout=15, query_string=True)
def get_customers():
    search = request.args.get("search", "")
    q      = f"%{search}%"
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT c.id, c.name, c.phone, c.email, c.address,
                   c.id_proof_type, c.id_proof_number, c.created_at,
                   COUNT(r.id) AS rent_count
            FROM customers c
            LEFT JOIN rentals r ON r.customer_id = c.id
            WHERE c.name LIKE %s OR c.phone LIKE %s OR c.email LIKE %s
            GROUP BY c.id
            ORDER BY c.id DESC
        """, (q, q, q))
        rows = cur.fetchall()
        dates_to_str(rows, ["created_at"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/customers", methods=["POST"])
def add_customer():
    d = request.json
    if not d.get("name") or not d.get("phone"):
        return err("Name and phone are required")
    conn, cur = get_db()
    try:
        cur.execute("""
            INSERT INTO customers (name, phone, email, address, id_proof_type, id_proof_number)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (d["name"], d["phone"], d.get("email",""), d.get("address",""),
              d.get("id_proof_type",""), d.get("id_proof_number","")))
        conn.commit()
        cache.clear()
        return ok({"id": cur.lastrowid}, "Customer added")
    except mysql.connector.IntegrityError as e:
        return err(str(e))
    finally:
        cur.close(); conn.close()

@app.route("/customers/<int:cid>", methods=["PUT"])
def update_customer(cid):
    d = request.json
    conn, cur = get_db()
    try:
        cur.execute("""
            UPDATE customers SET name=%s, phone=%s, email=%s, address=%s,
                   id_proof_type=%s, id_proof_number=%s
            WHERE id=%s
        """, (d["name"], d["phone"], d.get("email",""), d.get("address",""),
              d.get("id_proof_type",""), d.get("id_proof_number",""), cid))
        conn.commit()
        cache.clear()
        return ok(msg="Customer updated")
    finally:
        cur.close(); conn.close()

@app.route("/customers/<int:cid>", methods=["DELETE"])
def delete_customer(cid):
    conn, cur = get_db()
    try:
        cur.execute("SELECT COUNT(*) AS c FROM rentals WHERE customer_id=%s", (cid,))
        if cur.fetchone()["c"] > 0:
            return err("Cannot delete: customer has rental history")
        cur.execute("DELETE FROM customers WHERE id=%s", (cid,))
        conn.commit()
        cache.clear()
        return ok(msg="Customer deleted")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  EQUIPMENT
# ─────────────────────────────────────────────
@app.route("/equipment")
@cache.cached(timeout=15, query_string=True)
def get_equipment():
    search = request.args.get("search", "")
    cat    = request.args.get("category", "")
    status = request.args.get("status", "")
    q      = f"%{search}%"
    conn, cur = get_db()
    try:
        sql = """
            SELECT id, name, category, brand, model, serial_number,
                   daily_rate, deposit_amount, status, `condition`, description, created_at
            FROM equipment
            WHERE (name LIKE %s OR brand LIKE %s OR model LIKE %s)
        """
        params = [q, q, q]
        if cat:    sql += " AND category=%s";  params.append(cat)
        if status: sql += " AND status=%s";    params.append(status)
        sql += " ORDER BY id DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        dates_to_str(rows, ["created_at"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/equipment", methods=["POST"])
def add_equipment():
    d = request.json
    if not d.get("name") or not d.get("category") or not d.get("daily_rate"):
        return err("Name, category, and daily rate are required")
    conn, cur = get_db()
    try:
        cur.execute("""
            INSERT INTO equipment
              (name, category, brand, model, serial_number, daily_rate,
               deposit_amount, `condition`, description)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (d["name"], d["category"], d.get("brand",""), d.get("model",""),
              d.get("serial_number") or None, d["daily_rate"],
              d.get("deposit_amount",0), d.get("condition","Good"),
              d.get("description","")))
        conn.commit()
        cache.clear()
        return ok({"id": cur.lastrowid}, "Equipment added")
    except mysql.connector.IntegrityError as e:
        return err(str(e))
    finally:
        cur.close(); conn.close()

@app.route("/equipment/<int:eid>", methods=["PUT"])
def update_equipment(eid):
    d = request.json
    conn, cur = get_db()
    try:
        cur.execute("""
            UPDATE equipment SET name=%s, category=%s, brand=%s, model=%s,
              serial_number=%s, daily_rate=%s, deposit_amount=%s,
              `condition`=%s, description=%s
            WHERE id=%s
        """, (d["name"], d["category"], d.get("brand",""), d.get("model",""),
              d.get("serial_number") or None, d["daily_rate"],
              d.get("deposit_amount",0), d.get("condition","Good"),
              d.get("description",""), eid))
        conn.commit()
        cache.clear()
        return ok(msg="Equipment updated")
    finally:
        cur.close(); conn.close()

@app.route("/equipment/<int:eid>", methods=["DELETE"])
def delete_equipment(eid):
    conn, cur = get_db()
    try:
        cur.execute("SELECT status FROM equipment WHERE id=%s", (eid,))
        row = cur.fetchone()
        if not row: return err("Not found", 404)
        if row["status"] == "Rented":
            return err("Cannot delete: equipment is currently rented")
        cur.execute("DELETE FROM equipment WHERE id=%s", (eid,))
        conn.commit()
        cache.clear()
        return ok(msg="Equipment deleted")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  RENTALS
# ─────────────────────────────────────────────
@app.route("/rentals")
@cache.cached(timeout=15, query_string=True)
def get_rentals():
    search = request.args.get("search", "")
    status = request.args.get("status", "")
    q      = f"%{search}%"
    conn, cur = get_db()
    try:
        # 1. Auto-mark overdue
        cur.execute("""
            UPDATE rentals SET status='Overdue'
            WHERE status='Active'
              AND expected_return_date < CURDATE()
              AND actual_return_date IS NULL
        """)

        # 2. Auto-create late_fee records for overdue rentals that don't have one yet
        cur.execute("""
            INSERT IGNORE INTO late_fees (rental_id, days_late, fee_per_day, total_fee)
            SELECT r.id,
                   DATEDIFF(CURDATE(), r.expected_return_date),
                   500,
                   DATEDIFF(CURDATE(), r.expected_return_date) * 500
            FROM rentals r
            WHERE r.status = 'Overdue'
              AND r.actual_return_date IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM late_fees lf WHERE lf.rental_id = r.id
              )
        """)
        conn.commit()

        # 3. Fetch rentals with payment_status:
        #    "Paid"     — sum of Rental payments >= rental_amount
        #    "Not Paid" — otherwise
        sql = """
            SELECT r.id, c.name AS customer, e.name AS equipment,
                   r.start_date, r.expected_return_date, r.actual_return_date,
                   r.rental_amount, r.status, r.notes,
                   COALESCE(SUM(CASE WHEN p.payment_type='Rental' THEN p.amount ELSE 0 END), 0) AS paid_amount,
                   CASE
                     WHEN COALESCE(SUM(CASE WHEN p.payment_type='Rental' THEN p.amount ELSE 0 END), 0) >= r.rental_amount
                     THEN 'Paid'
                     ELSE 'Not Paid'
                   END AS payment_status
            FROM rentals r
            JOIN customers c ON r.customer_id = c.id
            JOIN equipment  e ON r.equipment_id = e.id
            LEFT JOIN payments p ON p.rental_id = r.id
            WHERE (c.name LIKE %s OR e.name LIKE %s)
        """
        params = [q, q]
        if status:
            sql += " AND r.status=%s"; params.append(status)
        sql += " GROUP BY r.id, c.name, e.name, r.start_date, r.expected_return_date, r.actual_return_date, r.rental_amount, r.status, r.notes"
        sql += " ORDER BY r.id DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        dates_to_str(rows, ["start_date", "expected_return_date", "actual_return_date"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/rentals", methods=["POST"])
def add_rental():
    d = request.json
    if not d.get("customer_id") or not d.get("equipment_id") \
       or not d.get("start_date") or not d.get("expected_return_date"):
        return err("customer_id, equipment_id, start_date, expected_return_date required")
    conn, cur = get_db()
    try:
        cur.execute("SELECT status, daily_rate, deposit_amount FROM equipment WHERE id=%s", (d["equipment_id"],))
        eq = cur.fetchone()
        if not eq: return err("Equipment not found", 404)
        if eq["status"] != "Available":
            return err("Equipment is not available")

        from datetime import date
        start         = date.fromisoformat(d["start_date"])
        end           = date.fromisoformat(d["expected_return_date"])
        days          = max(1, (end - start).days)
        rental_amount = d.get("rental_amount") or round(days * float(eq["daily_rate"]), 2)

        cur.execute("""
            INSERT INTO rentals
              (customer_id, equipment_id, start_date, expected_return_date,
               pickup_condition, rental_amount, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (d["customer_id"], d["equipment_id"], d["start_date"],
              d["expected_return_date"], d.get("pickup_condition","Good"),
              rental_amount, d.get("notes","")))
        rental_id = cur.lastrowid

        cur.execute("UPDATE equipment SET status='Rented' WHERE id=%s", (d["equipment_id"],))

        deposit_amt = float(eq["deposit_amount"] or 0)
        if deposit_amt > 0:
            cur.execute("INSERT INTO deposits (rental_id, amount_paid) VALUES (%s,%s)",
                        (rental_id, deposit_amt))

        conn.commit()
        cache.clear()
        return ok({"id": rental_id, "rental_amount": rental_amount,
                   "deposit_amount": deposit_amt}, "Rental created")
    finally:
        cur.close(); conn.close()

@app.route("/rentals/<int:rid>/return", methods=["POST"])
def process_return(rid):
    d = request.json
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT r.expected_return_date, r.equipment_id, e.deposit_amount
            FROM rentals r JOIN equipment e ON r.equipment_id=e.id
            WHERE r.id=%s
        """, (rid,))
        row = cur.fetchone()
        if not row: return err("Rental not found", 404)

        from datetime import date
        ret_date    = date.fromisoformat(d["return_date"])
        exp_date    = row["expected_return_date"]
        repair_cost = float(d.get("repair_cost", 0))
        condition   = d.get("condition", "Good")
        days_late   = max(0, (ret_date - exp_date).days)
        fee_per_day = 500.0
        late_fee    = days_late * fee_per_day
        deposit     = float(row["deposit_amount"] or 0)
        refund      = max(0, deposit - repair_cost - late_fee)

        new_eq_status = "Maintenance" if (condition == "Damaged" or repair_cost > 0) else "Available"

        cur.execute("""
            UPDATE rentals SET status='Returned', actual_return_date=%s, return_condition=%s
            WHERE id=%s
        """, (ret_date, condition, rid))
        cur.execute("UPDATE equipment SET status=%s, `condition`=%s WHERE id=%s",
                    (new_eq_status, condition, row["equipment_id"]))
        cur.execute("""
            UPDATE deposits SET damage_deduction=%s, late_fee_deduction=%s, refund_amount=%s
            WHERE rental_id=%s
        """, (repair_cost, late_fee, refund, rid))

        if days_late > 0:
            cur.execute("""
                INSERT IGNORE INTO late_fees (rental_id, days_late, fee_per_day, total_fee)
                VALUES (%s,%s,%s,%s)
            """, (rid, days_late, fee_per_day, late_fee))

        if repair_cost > 0 and d.get("damage_description"):
            cur.execute("""
                INSERT INTO damage_reports (rental_id, equipment_id, description, repair_cost, status)
                VALUES (%s,%s,%s,%s,'Pending')
            """, (rid, row["equipment_id"], d["damage_description"], repair_cost))

        conn.commit()
        cache.clear()
        return ok({
            "days_late":      days_late,
            "late_fee":       late_fee,
            "repair_cost":    repair_cost,
            "deposit_refund": refund
        }, "Return processed")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  PAYMENTS
# ─────────────────────────────────────────────
@app.route("/payments")
@cache.cached(timeout=15, query_string=True)
def get_payments():
    search   = request.args.get("search", "")
    pay_type = request.args.get("type", "")
    q        = f"%{search}%"
    conn, cur = get_db()
    try:
        sql = """
            SELECT p.id, p.rental_id, p.payment_type, p.amount,
                   p.payment_method, p.payment_date, p.notes
            FROM payments p
            WHERE (CAST(p.rental_id AS CHAR) LIKE %s OR p.notes LIKE %s)
        """
        params = [q, q]
        if pay_type:
            sql += " AND p.payment_type=%s"; params.append(pay_type)
        sql += " ORDER BY p.id DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        dates_to_str(rows, ["payment_date"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/payments", methods=["POST"])
def add_payment():
    d = request.json
    if not d.get("rental_id") or not d.get("amount"):
        return err("rental_id and amount required")
    conn, cur = get_db()
    try:
        cur.execute("""
            INSERT INTO payments (rental_id, payment_type, amount, payment_method, notes)
            VALUES (%s,%s,%s,%s,%s)
        """, (d["rental_id"], d.get("payment_type","Rental"),
              d["amount"], d.get("payment_method","Cash"), d.get("notes","")))
        if d.get("payment_type") == "Late Fee":
            cur.execute("UPDATE late_fees SET payment_status='Paid' WHERE rental_id=%s", (d["rental_id"],))
        conn.commit()
        cache.clear()
        return ok({"id": cur.lastrowid}, "Payment recorded")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  DEPOSITS
# ─────────────────────────────────────────────
@app.route("/deposits")
@cache.cached(timeout=15)
def get_deposits():
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT d.id, d.rental_id, c.name AS customer,
                   d.amount_paid, d.damage_deduction, d.late_fee_deduction,
                   d.refund_amount, d.refund_status, d.refund_date
            FROM deposits d
            JOIN rentals r  ON d.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            ORDER BY d.id DESC
        """)
        rows = cur.fetchall()
        dates_to_str(rows, ["refund_date"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/deposits/<int:did>/refund", methods=["POST"])
def process_refund(did):
    conn, cur = get_db()
    try:
        cur.execute("""
            UPDATE deposits SET refund_status='Processed', refund_date=CURDATE()
            WHERE id=%s
        """, (did,))
        conn.commit()
        cache.clear()
        return ok(msg="Refund processed")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  LATE FEES
# ─────────────────────────────────────────────
@app.route("/late_fees")
@cache.cached(timeout=15)
def get_late_fees():
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT lf.id, lf.rental_id, c.name AS customer,
                   lf.days_late, lf.fee_per_day, lf.total_fee, lf.payment_status
            FROM late_fees lf
            JOIN rentals r  ON lf.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            ORDER BY lf.id DESC
        """)
        return ok(cur.fetchall())
    finally:
        cur.close(); conn.close()

@app.route("/late_fees/<int:lid>/pay", methods=["POST"])
def pay_late_fee(lid):
    conn, cur = get_db()
    try:
        cur.execute("UPDATE late_fees SET payment_status='Paid' WHERE id=%s", (lid,))
        conn.commit()
        cache.clear()
        return ok(msg="Late fee marked paid")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  DAMAGE REPORTS
# ─────────────────────────────────────────────
@app.route("/damages")
@cache.cached(timeout=15)
def get_damages():
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT dr.id, dr.rental_id, e.name AS equipment,
                   dr.description, dr.repair_cost, dr.reported_at, dr.status
            FROM damage_reports dr
            JOIN equipment e ON dr.equipment_id = e.id
            ORDER BY dr.id DESC
        """)
        rows = cur.fetchall()
        dates_to_str(rows, ["reported_at"])
        return ok(rows)
    finally:
        cur.close(); conn.close()

@app.route("/damages", methods=["POST"])
def add_damage():
    d = request.json
    if not d.get("rental_id") or not d.get("equipment_id") or not d.get("description"):
        return err("rental_id, equipment_id, description required")
    conn, cur = get_db()
    try:
        cur.execute("""
            INSERT INTO damage_reports (rental_id, equipment_id, description, repair_cost, status)
            VALUES (%s,%s,%s,%s,%s)
        """, (d["rental_id"], d["equipment_id"], d["description"],
              d.get("repair_cost",0), d.get("status","Pending")))
        if d.get("status") != "Repaired":
            cur.execute("UPDATE equipment SET status='Maintenance' WHERE id=%s", (d["equipment_id"],))
        conn.commit()
        cache.clear()
        return ok({"id": cur.lastrowid}, "Damage report submitted")
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  REPORTS (cached longer — heavy query)
# ─────────────────────────────────────────────
@app.route("/reports")
@cache.cached(timeout=60)
def get_reports():
    conn, cur = get_db()
    try:
        cur.execute("SELECT COALESCE(SUM(amount),0) AS revenue FROM payments WHERE payment_type='Rental'")
        revenue = float(cur.fetchone()["revenue"])

        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM customers) AS customers,
                (SELECT COUNT(*) FROM rentals)   AS rentals,
                (SELECT COUNT(*) FROM damage_reports) AS damages
        """)
        counts = cur.fetchone()

        cur.execute("""
            SELECT category,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='Available' THEN 1 ELSE 0 END) AS available
            FROM equipment GROUP BY category
        """)
        categories = cur.fetchall()

        cur.execute("""
            SELECT c.name AS customer, e.name AS equipment,
                   DATEDIFF(CURDATE(), r.expected_return_date) AS days_late
            FROM rentals r
            JOIN customers c ON r.customer_id=c.id
            JOIN equipment  e ON r.equipment_id=e.id
            WHERE r.status='Overdue'
        """)
        overdue = cur.fetchall()

        return ok({
            "revenue":    revenue,
            "customers":  counts["customers"],
            "rentals":    counts["rentals"],
            "damages":    counts["damages"],
            "categories": categories,
            "overdue":    overdue
        })
    finally:
        cur.close(); conn.close()

# ─────────────────────────────────────────────
#  SELECTS (cached — rarely changes)
# ─────────────────────────────────────────────
@app.route("/selects")
@cache.cached(timeout=30)
def get_selects():
    conn, cur = get_db()
    try:
        cur.execute("SELECT id, name FROM customers ORDER BY name")
        customers = cur.fetchall()

        cur.execute("SELECT id, name FROM equipment WHERE status='Available' ORDER BY name")
        available_equipment = cur.fetchall()

        cur.execute("SELECT id, name FROM equipment ORDER BY name")
        all_equipment = cur.fetchall()

        cur.execute("""
            SELECT r.id, CONCAT('R#', r.id, ' — ', c.name, ' / ', e.name) AS label
            FROM rentals r
            JOIN customers c ON r.customer_id=c.id
            JOIN equipment  e ON r.equipment_id=e.id
            ORDER BY r.id DESC
        """)
        rentals = cur.fetchall()

        return ok({
            "customers":          customers,
            "available_equipment": available_equipment,
            "all_equipment":      all_equipment,
            "rentals":            rentals
        })
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    app.run(debug=True)