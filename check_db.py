import pyodbc

conn_str = 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=LPT2084-B1;DATABASE=Ixigo_TestAutomation;UID=myuser;PWD=MyPass135;Connection Timeout=30;MultipleActiveResultSets=True;'
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM ExtensionXpaths')
count = cursor.fetchone()[0]
print('Records in ExtensionXpaths:', count)

if count > 0:
    cursor.execute('SELECT TOP 10 id, element_name, xpath, page_name, session_id, created_at FROM ExtensionXpaths ORDER BY created_at DESC')
    rows = cursor.fetchall()
    for row in rows:
        print(f'ID: {row[0]}, Element: {row[1]}, XPath: {row[2][:50]}..., Page: {row[3]}, Session: {row[4]}, Time: {row[5]}')

conn.close()