from flask import Flask, jsonify, request
from flask_cors import CORS
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────
def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    return conn, cursor

def ok(data=None, msg="success"):
    return jsonify({"status": "ok", "message": msg, "data": data})

def err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code


# ─────────────────────────────────────────────
#  HOME
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return "RentFlow Backend Running ✅"


# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    conn, cur = get_db()
    try:
        cur.execute("SELECT COUNT(*) AS total FROM equipment")
        total_eq = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS avail FROM equipment WHERE status='Available'")
        avail_eq = cur.fetchone()["avail"]

        cur.execute("SELECT COUNT(*) AS active FROM rentals WHERE status='Active'")
        active_r = cur.fetchone()["active"]

        # Auto-update overdue
        cur.execute("""
            UPDATE rentals SET status='Overdue'
            WHERE status='Active'
              AND expected_return_date < CURDATE()
              AND actual_return_date IS NULL
        """)
        conn.commit()

        cur.execute("SELECT COUNT(*) AS overdue_count FROM rentals WHERE status='Overdue'")
        overdue_r = cur.fetchone()["overdue_count"]

        # Recent rentals
        cur.execute("""
            SELECT c.name AS customer, e.name AS equipment,
                   r.status, r.expected_return_date
            FROM rentals r
            JOIN customers c ON r.customer_id = c.id
            JOIN equipment  e ON r.equipment_id = e.id
            ORDER BY r.id DESC LIMIT 5
        """)
        recent_rentals = cur.fetchall()

        # Pending items
        cur.execute("""
            SELECT c.name, 'Deposit Refund' AS type, d.amount_paid AS amount
            FROM deposits d
            JOIN rentals r ON d.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            WHERE d.refund_status = 'Pending'
            UNION ALL
            SELECT c.name, 'Late Fee', lf.total_fee
            FROM late_fees lf
            JOIN rentals r ON lf.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            WHERE lf.payment_status = 'Unpaid'
            LIMIT 6
        """)
        pending = cur.fetchall()

        return ok({
            "total_equipment": total_eq,
            "available_equipment": avail_eq,
            "active_rentals": active_r,
            "overdue_rentals": overdue_r,
            "recent_rentals": recent_rentals,
            "pending_items": pending
        })
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  CUSTOMERS
# ─────────────────────────────────────────────
@app.route("/customers")
def get_customers():
    search = request.args.get("search", "")
    q = f"%{search}%"
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT c.id, c.name, c.phone, c.email, c.address,
                   c.id_proof_type, c.id_proof_number, c.created_at,
                   (SELECT COUNT(*) FROM rentals WHERE customer_id = c.id) AS rent_count
            FROM customers c
            WHERE c.name LIKE %s OR c.phone LIKE %s OR c.email LIKE %s
            ORDER BY c.id DESC
        """, (q, q, q))
        return ok(cur.fetchall())
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
        return ok(msg="Customer deleted")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  EQUIPMENT
# ─────────────────────────────────────────────
@app.route("/equipment")
def get_equipment():
    search = request.args.get("search", "")
    cat    = request.args.get("category", "")
    status = request.args.get("status", "")
    q = f"%{search}%"
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
        return ok(cur.fetchall())
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
              d.get("deposit_amount", 0), d.get("condition","Good"),
              d.get("description","")))
        conn.commit()
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
        return ok(msg="Equipment deleted")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  RENTALS
# ─────────────────────────────────────────────
@app.route("/rentals")
def get_rentals():
    search = request.args.get("search", "")
    status = request.args.get("status", "")
    q = f"%{search}%"
    conn, cur = get_db()
    try:
        # Auto-update overdue
        cur.execute("""
            UPDATE rentals SET status='Overdue'
            WHERE status='Active'
              AND expected_return_date < CURDATE()
              AND actual_return_date IS NULL
        """)
        conn.commit()

        sql = """
            SELECT r.id, c.name AS customer, e.name AS equipment,
                   r.start_date, r.expected_return_date, r.actual_return_date,
                   r.rental_amount, r.status, r.notes
            FROM rentals r
            JOIN customers c ON r.customer_id = c.id
            JOIN equipment  e ON r.equipment_id = e.id
            WHERE (c.name LIKE %s OR e.name LIKE %s)
        """
        params = [q, q]
        if status:
            sql += " AND r.status=%s"; params.append(status)
        sql += " ORDER BY r.id DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        # Convert dates to strings for JSON
        for r in rows:
            for k in ("start_date","expected_return_date","actual_return_date"):
                if r[k]: r[k] = str(r[k])
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
        # Check equipment is available
        cur.execute("SELECT status, daily_rate, deposit_amount FROM equipment WHERE id=%s", (d["equipment_id"],))
        eq = cur.fetchone()
        if not eq: return err("Equipment not found", 404)
        if eq["status"] != "Available":
            return err("Equipment is not available")

        # Calculate rental amount
        from datetime import date
        start = date.fromisoformat(d["start_date"])
        end   = date.fromisoformat(d["expected_return_date"])
        days  = max(1, (end - start).days)
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

        # Mark equipment as Rented
        cur.execute("UPDATE equipment SET status='Rented' WHERE id=%s", (d["equipment_id"],))

        # Create deposit record
        deposit_amt = float(eq["deposit_amount"] or 0)
        if deposit_amt > 0:
            cur.execute("""
                INSERT INTO deposits (rental_id, amount_paid) VALUES (%s,%s)
            """, (rental_id, deposit_amt))

        conn.commit()
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
            SELECT r.expected_return_date, r.equipment_id,
                   e.deposit_amount
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

        days_late = max(0, (ret_date - exp_date).days)
        fee_per_day = 500.0
        late_fee  = days_late * fee_per_day
        deposit   = float(row["deposit_amount"] or 0)
        refund    = max(0, deposit - repair_cost - late_fee)

        # Update rental
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
        return ok({
            "days_late": days_late,
            "late_fee": late_fee,
            "repair_cost": repair_cost,
            "deposit_refund": refund
        }, "Return processed")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  PAYMENTS
# ─────────────────────────────────────────────
@app.route("/payments")
def get_payments():
    search     = request.args.get("search", "")
    pay_type   = request.args.get("type", "")
    q = f"%{search}%"
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
        for r in rows:
            if r["payment_date"]: r["payment_date"] = str(r["payment_date"])
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
        return ok({"id": cur.lastrowid}, "Payment recorded")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  DEPOSITS
# ─────────────────────────────────────────────
@app.route("/deposits")
def get_deposits():
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT d.id, d.rental_id, c.name AS customer,
                   d.amount_paid, d.damage_deduction, d.late_fee_deduction,
                   d.refund_amount, d.refund_status, d.refund_date
            FROM deposits d
            JOIN rentals r ON d.rental_id = r.id
            JOIN customers c ON r.customer_id = c.id
            ORDER BY d.id DESC
        """)
        rows = cur.fetchall()
        for r in rows:
            if r["refund_date"]: r["refund_date"] = str(r["refund_date"])
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
        return ok(msg="Refund processed")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  LATE FEES
# ─────────────────────────────────────────────
@app.route("/late_fees")
def get_late_fees():
    conn, cur = get_db()
    try:
        cur.execute("""
            SELECT lf.id, lf.rental_id, c.name AS customer,
                   lf.days_late, lf.fee_per_day, lf.total_fee, lf.payment_status
            FROM late_fees lf
            JOIN rentals r ON lf.rental_id = r.id
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
        return ok(msg="Late fee marked paid")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  DAMAGE REPORTS
# ─────────────────────────────────────────────
@app.route("/damages")
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
        for r in rows:
            if r["reported_at"]: r["reported_at"] = str(r["reported_at"])
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
        return ok({"id": cur.lastrowid}, "Damage report submitted")
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  REPORTS
# ─────────────────────────────────────────────
@app.route("/reports")
def get_reports():
    conn, cur = get_db()
    try:
        cur.execute("SELECT COALESCE(SUM(amount),0) AS revenue FROM payments WHERE payment_type='Rental'")
        revenue = float(cur.fetchone()["revenue"])

        cur.execute("SELECT COUNT(*) AS c FROM customers")
        customers = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM rentals")
        rentals = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM damage_reports")
        damages = cur.fetchone()["c"]

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
            "revenue": revenue,
            "customers": customers,
            "rentals": rentals,
            "damages": damages,
            "categories": categories,
            "overdue": overdue
        })
    finally:
        cur.close(); conn.close()


# ─────────────────────────────────────────────
#  SELECTS (for dropdown population)
# ─────────────────────────────────────────────
@app.route("/selects")
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
            "customers": customers,
            "available_equipment": available_equipment,
            "all_equipment": all_equipment,
            "rentals": rentals
        })
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    app.run(debug=True)