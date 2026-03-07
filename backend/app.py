from flask import Flask, jsonify
from flask_cors import CORS
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)
CORS(app)

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

@app.route("/")
def home():
    return "RentFlow Backend Running"

@app.route("/equipment")
def get_equipment():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM equipment")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)

@app.route("/customers")
def get_customers():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM customers")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)

@app.route("/rentals")
def get_rentals():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM rentals")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)