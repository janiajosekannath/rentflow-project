-- ============================================================
--  RentFlow — Equipment Rental Management System
--  MySQL Database Schema + Sample Data
--  DBMS Project | 7 Tables | Fully Normalized
-- ============================================================

-- Step 1: Create and select the database
CREATE DATABASE IF NOT EXISTS rentflow_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rentflow_db;

-- ============================================================
-- TABLE 1: customers
-- ============================================================
CREATE TABLE customers (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    phone            VARCHAR(20)  NOT NULL,
    email            VARCHAR(100),
    address          TEXT,
    id_proof_type    VARCHAR(50),
    id_proof_number  VARCHAR(50),
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_phone (phone)
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 3: admin
-- ============================================================
CREATE TABLE admins (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    name     VARCHAR(100),
    email    VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role     ENUM('admin', 'client') DEFAULT 'admin'
);

-- Insert a test admin
INSERT INTO admins (name, email, password, role)
VALUES ('Admin User', 'admin@rentflow.com', 'admin123', 'admin');

-- ============================================================
-- TABLE 2: equipment
-- ============================================================
CREATE TABLE equipment (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(150) NOT NULL,
    category         ENUM('Cameras','Laptops','Projectors','Musical Instruments','Audio Equipment','Other') NOT NULL,
    brand            VARCHAR(80),
    model            VARCHAR(80),
    serial_number    VARCHAR(80) UNIQUE,
    daily_rate       DECIMAL(10,2) NOT NULL,
    deposit_amount   DECIMAL(10,2) DEFAULT 0,
    status           ENUM('Available','Rented','Maintenance') DEFAULT 'Available',
    `condition`      ENUM('Excellent','Good','Fair','Damaged') DEFAULT 'Good',
    description      TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 3: rentals
-- ============================================================
CREATE TABLE rentals (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    customer_id          INT NOT NULL,
    equipment_id         INT NOT NULL,
    start_date           DATE NOT NULL,
    expected_return_date DATE NOT NULL,
    actual_return_date   DATE,
    pickup_condition     ENUM('Excellent','Good','Fair') DEFAULT 'Good',
    return_condition     ENUM('Excellent','Good','Fair','Damaged'),
    rental_amount        DECIMAL(10,2) NOT NULL,
    status               ENUM('Active','Returned','Overdue') DEFAULT 'Active',
    notes                TEXT,
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id)  REFERENCES customers(id)  ON DELETE RESTRICT,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id)  ON DELETE RESTRICT,
    INDEX idx_customer  (customer_id),
    INDEX idx_equipment (equipment_id),
    INDEX idx_status    (status)
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 4: deposits
-- ============================================================
CREATE TABLE deposits (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    rental_id           INT NOT NULL UNIQUE,
    amount_paid         DECIMAL(10,2) NOT NULL,
    damage_deduction    DECIMAL(10,2) DEFAULT 0,
    late_fee_deduction  DECIMAL(10,2) DEFAULT 0,
    refund_amount       DECIMAL(10,2),
    refund_status       ENUM('Pending','Processed','Waived') DEFAULT 'Pending',
    refund_date         DATE,
    FOREIGN KEY (rental_id) REFERENCES rentals(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 5: late_fees
-- ============================================================
CREATE TABLE late_fees (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    rental_id       INT NOT NULL UNIQUE,
    days_late       INT NOT NULL,
    fee_per_day     DECIMAL(10,2) NOT NULL DEFAULT 500.00,
    total_fee       DECIMAL(10,2) NOT NULL,
    payment_status  ENUM('Unpaid','Paid') DEFAULT 'Unpaid',
    FOREIGN KEY (rental_id) REFERENCES rentals(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 6: payments
-- ============================================================
CREATE TABLE payments (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    rental_id       INT NOT NULL,
    payment_type    ENUM('Rental','Deposit','Late Fee','Damage','Refund') NOT NULL,
    amount          DECIMAL(10,2) NOT NULL,
    payment_method  ENUM('Cash','Card','UPI','Bank Transfer') DEFAULT 'Cash',
    payment_date    DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes           VARCHAR(255),
    FOREIGN KEY (rental_id) REFERENCES rentals(id) ON DELETE CASCADE,
    INDEX idx_payment_rental (rental_id),
    INDEX idx_payment_type   (payment_type)
) ENGINE=InnoDB;

-- ============================================================
-- TABLE 7: damage_reports
-- ============================================================
CREATE TABLE damage_reports (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    rental_id    INT NOT NULL,
    equipment_id INT NOT NULL,
    description  TEXT NOT NULL,
    repair_cost  DECIMAL(10,2) DEFAULT 0,
    status       ENUM('Pending','Under Repair','Repaired') DEFAULT 'Pending',
    reported_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (rental_id)    REFERENCES rentals(id)   ON DELETE CASCADE,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE RESTRICT,
    INDEX idx_damage_equipment (equipment_id)
) ENGINE=InnoDB;


-- ============================================================
--  SAMPLE DATA
-- ============================================================

-- Customers (5 records)
INSERT INTO customers (name, phone, email, address, id_proof_type, id_proof_number) VALUES
('Rahul Sharma',  '9876543210', 'rahul@email.com',  '12, MG Road, Bangalore',          'Aadhar Card',     '1234-5678-9012'),
('Priya Patel',   '8765432109', 'priya@email.com',  '45, Linking Road, Mumbai',         'PAN Card',        'ABCDE1234F'),
('Arjun Kumar',   '7654321098', 'arjun@email.com',  '78, Connaught Place, New Delhi',   'Passport',        'P1234567'),
('Sneha Reddy',   '6543210987', 'sneha@email.com',  '23, Jubilee Hills, Hyderabad',     'Aadhar Card',     '9876-5432-1098'),
('Vikram Mehta',  '9988776655', 'vikram@email.com', '56, CG Road, Ahmedabad',           'Driving License', 'GJ01-DL-2019');

-- Equipment (8 records)
INSERT INTO equipment (name, category, brand, model, serial_number, daily_rate, deposit_amount, status, `condition`, description) VALUES
('DSLR Camera Pro',       'Cameras',              'Canon',  'EOS R5',        'CAM-001', 1500.00, 15000.00, 'Available',   'Excellent', '45MP full-frame mirrorless camera with 8K video'),
('MacBook Pro 16"',       'Laptops',              'Apple',  'MacBook Pro M3','LAP-001', 2000.00, 20000.00, 'Rented',      'Good',      '16-inch M3 Pro chip, 18GB RAM, 512GB SSD'),
('4K Projector',          'Projectors',           'Epson',  'EH-TW9400',     'PRO-001', 1200.00, 10000.00, 'Available',   'Excellent', '4K HDR home theater projector, 2600 lumens'),
('Acoustic Guitar',       'Musical Instruments',  'Yamaha', 'FG800',         'GIT-001',  300.00,  3000.00, 'Available',   'Good',      'Full-size dreadnought acoustic guitar'),
('Professional Drone',    'Cameras',              'DJI',    'Mavic 3 Pro',   'DRN-001', 2500.00, 25000.00, 'Maintenance', 'Fair',      'Professional drone with Hasselblad camera'),
('PA Speaker System',     'Audio Equipment',      'JBL',    'EON715',        'SPK-001',  800.00,  8000.00, 'Available',   'Good',      '1300W powered PA speaker, 15-inch woofer'),
('Gaming Laptop',         'Laptops',              'ASUS',   'ROG Strix G16', 'LAP-002', 1800.00, 18000.00, 'Available',   'Excellent', 'RTX 4070, Intel i9, 32GB RAM'),
('Mirrorless Camera',     'Cameras',              'Sony',   'Alpha A7 IV',   'CAM-002', 1800.00, 18000.00, 'Rented',      'Good',      '33MP full-frame mirrorless, 4K 60fps video');

-- Rentals (5 records)
INSERT INTO rentals (customer_id, equipment_id, start_date, expected_return_date, actual_return_date, pickup_condition, return_condition, rental_amount, status, notes) VALUES
(1, 2, CURDATE() - INTERVAL 10 DAY, CURDATE() - INTERVAL 3 DAY, NULL,          'Good',      NULL,          20000.00, 'Overdue',  'Corporate event — MacBook needed for presentation'),
(2, 8, CURDATE() - INTERVAL 5 DAY,  CURDATE() + INTERVAL 2 DAY, NULL,          'Good',      NULL,           9000.00, 'Active',   'Wedding photography project'),
(3, 3, CURDATE() - INTERVAL 2 DAY,  CURDATE() + INTERVAL 5 DAY, NULL,          'Excellent', NULL,           8400.00, 'Active',   'Conference room presentation'),
(4, 4, CURDATE() - INTERVAL 20 DAY, CURDATE() - INTERVAL 13 DAY, CURDATE() - INTERVAL 13 DAY, 'Good', 'Good', 2100.00, 'Returned', 'Music recital rehearsal'),
(5, 6, CURDATE() - INTERVAL 8 DAY,  CURDATE() - INTERVAL 1 DAY, CURDATE() - INTERVAL 1 DAY,  'Good', 'Good', 5600.00, 'Returned', 'Outdoor concert event');

-- Deposits (5 records — one per rental)
INSERT INTO deposits (rental_id, amount_paid, damage_deduction, late_fee_deduction, refund_amount, refund_status, refund_date) VALUES
(1, 20000.00, 0,    0,    NULL,     'Pending',   NULL),
(2, 18000.00, 0,    0,    NULL,     'Pending',   NULL),
(3, 10000.00, 0,    0,    NULL,     'Pending',   NULL),
(4,  3000.00, 0,    0,    3000.00,  'Processed', CURDATE() - INTERVAL 12 DAY),
(5,  8000.00, 0,    500,  7500.00,  'Processed', CURDATE());

-- Late Fees (2 records)
INSERT INTO late_fees (rental_id, days_late, fee_per_day, total_fee, payment_status) VALUES
(1, 3,  500.00, 1500.00, 'Unpaid'),   -- Rental 1 is overdue by 3 days
(5, 1,  500.00,  500.00, 'Paid');     -- Rental 5 was 1 day late but paid

-- Payments (10 records)
INSERT INTO payments (rental_id, payment_type, amount, payment_method, notes) VALUES
(1, 'Deposit',  20000.00, 'UPI',           'Security deposit for MacBook'),
(1, 'Rental',   14000.00, 'Cash',          'Partial rental payment upfront'),
(2, 'Deposit',  18000.00, 'Card',          'Security deposit for Sony Camera'),
(2, 'Rental',    9000.00, 'UPI',           'Full rental amount paid'),
(3, 'Deposit',  10000.00, 'Cash',          'Projector security deposit'),
(3, 'Rental',    8400.00, 'UPI',           'Full rental for 7 days'),
(4, 'Deposit',   3000.00, 'Cash',          'Guitar deposit'),
(4, 'Rental',    2100.00, 'Cash',          'Guitar rental 7 days'),
(5, 'Deposit',   8000.00, 'UPI',           'Speaker system deposit'),
(5, 'Rental',    5600.00, 'Card',          'Speaker rental 7 days'),
(5, 'Late Fee',   500.00, 'Cash',          'Late fee for 1 day overdue'),
(4, 'Refund',    3000.00, 'Bank Transfer', 'Full deposit refund — no damage');

-- Damage Reports (1 record)
INSERT INTO damage_reports (rental_id, equipment_id, description, repair_cost, status) VALUES
(1, 5, 'Drone propeller cracked during transport, gimbal slightly misaligned', 3500.00, 'Under Repair');


-- ============================================================
--  USEFUL VIEWS (bonus for your project)
-- ============================================================

-- View: Active rentals with customer & equipment details
CREATE OR REPLACE VIEW vw_active_rentals AS
SELECT
    r.id            AS rental_id,
    c.name          AS customer_name,
    c.phone         AS customer_phone,
    e.name          AS equipment_name,
    e.category,
    r.start_date,
    r.expected_return_date,
    r.rental_amount,
    r.status,
    DATEDIFF(CURDATE(), r.expected_return_date) AS days_overdue
FROM rentals r
JOIN customers c  ON r.customer_id  = c.id
JOIN equipment e  ON r.equipment_id = e.id
WHERE r.status IN ('Active', 'Overdue');

-- View: Equipment utilization summary
CREATE OR REPLACE VIEW vw_equipment_utilization AS
SELECT
    e.id,
    e.name,
    e.category,
    e.status,
    e.daily_rate,
    COUNT(r.id)           AS total_rentals,
    COALESCE(SUM(r.rental_amount), 0) AS total_revenue
FROM equipment e
LEFT JOIN rentals r ON e.id = r.equipment_id
GROUP BY e.id, e.name, e.category, e.status, e.daily_rate;

-- View: Customer rental summary
CREATE OR REPLACE VIEW vw_customer_summary AS
SELECT
    c.id,
    c.name,
    c.phone,
    COUNT(r.id)                          AS total_rentals,
    COALESCE(SUM(r.rental_amount), 0)    AS total_spent,
    SUM(CASE WHEN r.status = 'Active'   THEN 1 ELSE 0 END) AS active_rentals,
    SUM(CASE WHEN r.status = 'Overdue'  THEN 1 ELSE 0 END) AS overdue_rentals
FROM customers c
LEFT JOIN rentals r ON c.id = r.customer_id
GROUP BY c.id, c.name, c.phone;

-- View: Pending deposit refunds
CREATE OR REPLACE VIEW vw_pending_refunds AS
SELECT
    d.id            AS deposit_id,
    r.id            AS rental_id,
    c.name          AS customer_name,
    e.name          AS equipment_name,
    d.amount_paid,
    d.damage_deduction,
    d.late_fee_deduction,
    (d.amount_paid - d.damage_deduction - d.late_fee_deduction) AS refund_due
FROM deposits d
JOIN rentals   r ON d.rental_id    = r.id
JOIN customers c ON r.customer_id  = c.id
JOIN equipment e ON r.equipment_id = e.id
WHERE d.refund_status = 'Pending';


-- ============================================================
--  STORED PROCEDURES (bonus)
-- ============================================================

DELIMITER $$

-- Procedure: Process a rental return
CREATE PROCEDURE sp_process_return(
    IN  p_rental_id    INT,
    IN  p_return_date  DATE,
    IN  p_condition    ENUM('Excellent','Good','Fair','Damaged'),
    IN  p_repair_cost  DECIMAL(10,2)
)
BEGIN
    DECLARE v_expected_date  DATE;
    DECLARE v_equipment_id   INT;
    DECLARE v_deposit_amount DECIMAL(10,2);
    DECLARE v_days_late      INT;
    DECLARE v_late_fee       DECIMAL(10,2);
    DECLARE v_refund         DECIMAL(10,2);
    DECLARE v_fee_per_day    DECIMAL(10,2) DEFAULT 500.00;

    -- Get rental details
    SELECT expected_return_date, equipment_id
    INTO   v_expected_date, v_equipment_id
    FROM   rentals WHERE id = p_rental_id;

    -- Get deposit amount
    SELECT deposit_amount INTO v_deposit_amount
    FROM   equipment WHERE id = v_equipment_id;

    -- Calculate late fee
    SET v_days_late = GREATEST(0, DATEDIFF(p_return_date, v_expected_date));
    SET v_late_fee  = v_days_late * v_fee_per_day;
    SET v_refund    = GREATEST(0, v_deposit_amount - p_repair_cost - v_late_fee);

    -- Update rental
    UPDATE rentals
    SET status = 'Returned',
        actual_return_date = p_return_date,
        return_condition   = p_condition
    WHERE id = p_rental_id;

    -- Update equipment status
    UPDATE equipment
    SET status    = IF(p_condition = 'Damaged' OR p_repair_cost > 0, 'Maintenance', 'Available'),
        `condition` = p_condition
    WHERE id = v_equipment_id;

    -- Update deposit
    UPDATE deposits
    SET damage_deduction   = p_repair_cost,
        late_fee_deduction = v_late_fee,
        refund_amount      = v_refund
    WHERE rental_id = p_rental_id;

    -- Insert late fee record if applicable
    IF v_days_late > 0 THEN
        INSERT IGNORE INTO late_fees (rental_id, days_late, fee_per_day, total_fee)
        VALUES (p_rental_id, v_days_late, v_fee_per_day, v_late_fee);
    END IF;

    SELECT CONCAT('Return processed. Late days: ', v_days_late,
                  ' | Late fee: ₹', v_late_fee,
                  ' | Refund: ₹', v_refund) AS result;
END$$

DELIMITER ;


-- ============================================================
--  SAMPLE QUERIES to verify data
-- ============================================================

-- 1. All customers
-- SELECT * FROM customers;

-- 2. Available equipment
-- SELECT * FROM equipment WHERE status = 'Available';

-- 3. Active/Overdue rentals with details
-- SELECT * FROM vw_active_rentals;

-- 4. Revenue summary
-- SELECT payment_type, SUM(amount) AS total FROM payments GROUP BY payment_type;

-- 5. Overdue rentals
-- SELECT rental_id, customer_name, equipment_name, days_overdue FROM vw_active_rentals WHERE days_overdue > 0;

-- 6. Customer spending summary
-- SELECT * FROM vw_customer_summary ORDER BY total_spent DESC;

-- 7. Pending refunds
-- SELECT * FROM vw_pending_refunds;

-- 8. Equipment utilization
-- SELECT * FROM vw_equipment_utilization ORDER BY total_revenue DESC;

-- ============================================================
--  Done! Run: USE rentflow_db; SHOW TABLES;
-- ============================================================
