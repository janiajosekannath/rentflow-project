from config import DB_CONFIG
import mysql.connector

conn = mysql.connector.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        role ENUM('admin', 'client') DEFAULT 'admin'
    )
""")

cur.execute("""
    INSERT IGNORE INTO admins (name, email, password, role)
    VALUES ('Admin User', 'admin@rentflow.com', 'admin123', 'admin')
""")

conn.commit()
conn.close()
print('admins table created successfully ✅')