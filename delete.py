import sqlite3

# Connect to the SQLite database
conn = sqlite3.connect('database/admissions.db')
cursor = conn.cursor()

# Delete all records from Admission_Results table
cursor.execute("DELETE FROM Admission_Results")

# Delete all records from Admission_Seats table
cursor.execute("DELETE FROM Application_Data")

# Commit the changes and close the connection
conn.commit()
conn.close()

print("Records deleted successfully.")
