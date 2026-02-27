# Smart XPath Capture - Flask Backend API
# Flask API endpoint to receive and store XPath data from Chrome Extension

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome Extension

# Database configuration
DATABASE = 'xpath_capture.db'

def init_database():
    """Initialize the SQLite database for storing XPath data"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create table for storing XPath captures
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS xpath_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            xpath TEXT NOT NULL,
            candidates TEXT,
            metadata TEXT,
            url TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            score INTEGER,
            tag_name TEXT,
            element_text TEXT
        )
    ''')
    
    # Create table for API usage statistics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status_code INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Smart XPath Capture API',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/save-xpath', methods=['POST', 'OPTIONS'])
def save_xpath():
    """Save XPath data from Chrome Extension"""
    try:
        # Handle preflight requests
        if request.method == 'OPTIONS':
            return '', 200
            
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Validate required fields
        required_fields = ['xpath']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'message': f'Missing required fields: {missing_fields}'
            }), 400
        
        # Extract data
        xpath = data['xpath']
        candidates = data.get('candidates', [])
        metadata = data.get('metadata', {})
        url = data.get('url', '')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        score = data.get('score', 0)
        
        # Extract useful info from metadata
        tag_name = metadata.get('tagName', '')
        element_text = metadata.get('innerText', '')[:100]  # Limit text length
        
        # Store in database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO xpath_captures 
            (xpath, candidates, metadata, url, timestamp, score, tag_name, element_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            xpath,
            json.dumps(candidates),
            json.dumps(metadata),
            url,
            timestamp,
            score,
            tag_name,
            element_text
        ))
        
        capture_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Log API usage
        log_api_usage('/api/save-xpath', 'POST', 200)
        
        return jsonify({
            'success': True,
            'message': 'XPath saved successfully',
            'capture_id': capture_id,
            'xpath': xpath,
            'score': score
        }), 201
        
    except Exception as e:
        print(f"Error saving XPath: {str(e)}")
        log_api_usage('/api/save-xpath', 'POST', 500)
        
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/xpaths', methods=['GET'])
def get_xpaths():
    """Get all saved XPath captures"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get query parameters
        limit = request.args.get('limit', 100, type=int)
        tag_filter = request.args.get('tag', '')
        url_filter = request.args.get('url', '')
        
        # Build query
        query = '''
            SELECT id, xpath, candidates, metadata, url, timestamp, score, tag_name, element_text
            FROM xpath_captures
            WHERE 1=1
        '''
        params = []
        
        if tag_filter:
            query += ' AND tag_name LIKE ?'
            params.append(f'%{tag_filter}%')
            
        if url_filter:
            query += ' AND url LIKE ?'
            params.append(f'%{url_filter}%')
            
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        xpaths = []
        for row in rows:
            xpaths.append({
                'id': row[0],
                'xpath': row[1],
                'candidates': json.loads(row[2]) if row[2] else [],
                'metadata': json.loads(row[3]) if row[3] else {},
                'url': row[4],
                'timestamp': row[5],
                'score': row[6],
                'tag_name': row[7],
                'element_text': row[8]
            })
        
        log_api_usage('/api/xpaths', 'GET', 200)
        
        return jsonify({
            'success': True,
            'count': len(xpaths),
            'xpaths': xpaths
        })
        
    except Exception as e:
        print(f"Error retrieving XPaths: {str(e)}")
        log_api_usage('/api/xpaths', 'GET', 500)
        
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/xpaths/<int:xpath_id>', methods=['GET'])
def get_xpath(xpath_id):
    """Get specific XPath by ID"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, xpath, candidates, metadata, url, timestamp, score, tag_name, element_text
            FROM xpath_captures
            WHERE id = ?
        ''', (xpath_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                'success': False,
                'message': 'XPath not found'
            }), 404
        
        xpath_data = {
            'id': row[0],
            'xpath': row[1],
            'candidates': json.loads(row[2]) if row[2] else [],
            'metadata': json.loads(row[3]) if row[3] else {},
            'url': row[4],
            'timestamp': row[5],
            'score': row[6],
            'tag_name': row[7],
            'element_text': row[8]
        }
        
        log_api_usage(f'/api/xpaths/{xpath_id}', 'GET', 200)
        
        return jsonify({
            'success': True,
            'xpath': xpath_data
        })
        
    except Exception as e:
        print(f"Error retrieving XPath {xpath_id}: {str(e)}")
        log_api_usage(f'/api/xpaths/{xpath_id}', 'GET', 500)
        
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/xpaths/<int:xpath_id>', methods=['DELETE'])
def delete_xpath(xpath_id):
    """Delete specific XPath by ID"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM xpath_captures WHERE id = ?', (xpath_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'XPath not found'
            }), 404
        
        conn.commit()
        conn.close()
        
        log_api_usage(f'/api/xpaths/{xpath_id}', 'DELETE', 200)
        
        return jsonify({
            'success': True,
            'message': f'XPath with ID {xpath_id} deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting XPath {xpath_id}: {str(e)}")
        log_api_usage(f'/api/xpaths/{xpath_id}', 'DELETE', 500)
        
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get API usage statistics"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get total captures
        cursor.execute('SELECT COUNT(*) FROM xpath_captures')
        total_captures = cursor.fetchone()[0]
        
        # Get recent captures (last 24 hours)
        cursor.execute('''
            SELECT COUNT(*) FROM xpath_captures 
            WHERE timestamp > datetime('now', '-1 day')
        ''')
        recent_captures = cursor.fetchone()[0]
        
        # Get most common tag names
        cursor.execute('''
            SELECT tag_name, COUNT(*) as count
            FROM xpath_captures
            WHERE tag_name != ''
            GROUP BY tag_name
            ORDER BY count DESC
            LIMIT 10
        ''')
        common_tags = [{'tag': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Get API usage stats
        cursor.execute('''
            SELECT endpoint, method, COUNT(*) as requests
            FROM api_usage
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY endpoint, method
            ORDER BY requests DESC
        ''')
        api_usage = [{'endpoint': row[0], 'method': row[1], 'requests': row[2]} for row in cursor.fetchall()]
        
        conn.close()
        
        log_api_usage('/api/stats', 'GET', 200)
        
        return jsonify({
            'success': True,
            'stats': {
                'total_captures': total_captures,
                'recent_captures': recent_captures,
                'common_tags': common_tags,
                'api_usage': api_usage
            }
        })
        
    except Exception as e:
        print(f"Error getting stats: {str(e)}")
        log_api_usage('/api/stats', 'GET', 500)
        
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/', methods=['GET'])
def dashboard():
    """Simple HTML dashboard to view captured XPaths"""
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart XPath Capture Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; margin-bottom: 30px; }
            .stats { display: flex; gap: 20px; margin-bottom: 30px; }
            .stat-card { background: #667eea; color: white; padding: 20px; border-radius: 6px; text-align: center; }
            .stat-value { font-size: 2em; font-weight: bold; }
            .stat-label { font-size: 0.9em; opacity: 0.9; }
            .xpath-list { margin-top: 30px; }
            .xpath-item { background: #f8f9fa; padding: 15px; margin-bottom: 10px; border-radius: 6px; border-left: 4px solid #667eea; }
            .xpath-text { font-family: 'Courier New', monospace; background: #333; color: #0f0; padding: 8px; border-radius: 4px; margin: 5px 0; }
            .metadata { font-size: 0.9em; color: #666; margin-top: 5px; }
            .btn { background: #667eea; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; margin: 5px; }
            .btn:hover { background: #5a6fd8; }
            .error { color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 Smart XPath Capture Dashboard</h1>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value" id="totalCaptures">-</div>
                    <div class="stat-label">Total Captures</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="recentCaptures">-</div>
                    <div class="stat-label">Recent (24h)</div>
                </div>
            </div>
            
            <div>
                <button class="btn" onclick="refreshData()">Refresh Data</button>
                <button class="btn" onclick="exportData()">Export JSON</button>
            </div>
            
            <div id="xpathList" class="xpath-list">
                Loading XPaths...
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('totalCaptures').textContent = data.stats.total_captures;
                        document.getElementById('recentCaptures').textContent = data.stats.recent_captures;
                    }
                } catch (error) {
                    console.error('Error loading stats:', error);
                }
            }
            
            async function loadXPaths() {
                try {
                    const response = await fetch('/api/xpaths?limit=50');
                    const data = await response.json();
                    
                    const container = document.getElementById('xpathList');
                    
                    if (data.success && data.xpaths.length > 0) {
                        container.innerHTML = data.xpaths.map(xpath => `
                            <div class="xpath-item">
                                <div class="xpath-text">${xpath.xpath}</div>
                                <div class="metadata">
                                    <strong>Score:</strong> ${xpath.score}/100 | 
                                    <strong>Tag:</strong> ${xpath.tag_name} | 
                                    <strong>URL:</strong> ${xpath.url} | 
                                    <strong>Time:</strong> ${new Date(xpath.timestamp).toLocaleString()}
                                </div>
                                ${xpath.element_text ? `<div class="metadata"><strong>Text:</strong> ${xpath.element_text}</div>` : ''}
                                <div style="margin-top: 10px;">
                                    <button class="btn" onclick="testXPath('${xpath.xpath}')">Test</button>
                                    <button class="btn" onclick="deleteXPath(${xpath.id})">Delete</button>
                                </div>
                            </div>
                        `).join('');
                    } else {
                        container.innerHTML = '<p>No XPaths captured yet.</p>';
                    }
                } catch (error) {
                    console.error('Error loading XPaths:', error);
                    document.getElementById('xpathList').innerHTML = '<div class="error">Error loading XPaths</div>';
                }
            }
            
            async function refreshData() {
                await loadStats();
                await loadXPaths();
            }
            
            async function deleteXPath(id) {
                if (confirm('Are you sure you want to delete this XPath?')) {
                    try {
                        const response = await fetch('/api/xpaths/' + id, { method: 'DELETE' });
                        const data = await response.json();
                        
                        if (data.success) {
                            alert('XPath deleted successfully');
                            refreshData();
                        } else {
                            alert('Error deleting XPath: ' + data.message);
                        }
                    } catch (error) {
                        alert('Error: ' + error.message);
                    }
                }
            }
            
            function testXPath(xpath) {
                // This would need to be implemented to test on the dashboard page
                alert('Testing XPath: ' + xpath + '\\n(Feature would open new tab to test)');
            }
            
            function exportData() {
                fetch('/api/xpaths?limit=1000')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const blob = new Blob([JSON.stringify(data.xpaths, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'xpath-exports-' + new Date().toISOString().split('T')[0] + '.json';
                        a.click();
                        URL.revokeObjectURL(url);
                    }
                });
            }
            
            // Load data on page load
            refreshData();
        </script>
    </body>
    </html>
    '''
    
    return render_template_string(html_template)

def log_api_usage(endpoint, method, status_code):
    """Log API usage for statistics"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO api_usage (endpoint, method, status_code)
            VALUES (?, ?, ?)
        ''', (endpoint, method, status_code))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging API usage: {e}")

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    print("Smart XPath Capture API Server Starting...")
    print("Dashboard: http://127.0.0.1:5000/")
    print("Health Check: http://127.0.0.1:5000/api/health")
    print("API Endpoint: http://127.0.0.1:5000/api/save-xpath")
    
    # Run the Flask app
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=False  # Avoid double execution in some environments
    )