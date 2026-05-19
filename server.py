import http.server
import json
import os
import subprocess
from datetime import datetime, timedelta

PORT = 5050
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
INTERVALS = [1, 3, 7, 14, 30, 60]


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"topics": []}


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def ensure_calendar():
    script = '''
tell application "Calendar"
    if not (exists calendar "Spaced Repetition") then
        make new calendar with properties {name:"Spaced Repetition"}
    end if
end tell
'''
    subprocess.run(['osascript', '-e', script], capture_output=True)


def add_review_to_calendar(topic, category, date_learned_str, notes, review_dates):
    ensure_calendar()
    base = datetime.strptime(date_learned_str, '%Y-%m-%d')
    for review_str in review_dates:
        dt = datetime.strptime(review_str, '%Y-%m-%d')
        day_num = (dt - base).days
        label = f"Review (Day {day_num}): {topic}"
        # AppleScript date: "Monday, 18 May 2026 at 9:00:00 AM"  (system locale format)
        as_date = dt.strftime('%A, %-d %B %Y') + ' at 9:00:00 AM'
        as_end  = dt.strftime('%A, %-d %B %Y') + ' at 9:30:00 AM'
        desc = f"Category: {category}\nDay {day_num} spaced repetition review"
        if notes:
            desc += f"\nNotes: {notes}"
        # Escape for AppleScript
        label_esc = label.replace('"', '\\"')
        desc_esc  = desc.replace('"', '\\"').replace('\n', '\\n')
        script = f'''
tell application "Calendar"
    tell calendar "Spaced Repetition"
        set sDate to date "{as_date}"
        set eDate to date "{as_end}"
        make new event with properties {{summary:"{label_esc}", start date:sDate, end date:eDate, description:"{desc_esc}"}}
    end tell
end tell
'''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"AppleScript error for {review_str}: {result.stderr}")


class Handler(http.server.BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._serve_file('index.html', 'text/html; charset=utf-8')
        elif self.path == '/topics':
            self._send_json(load_data())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/add-topic':
            topic    = body.get('topic', '').strip()
            category = body.get('category', 'Physiology')
            date_str = body.get('date', datetime.today().strftime('%Y-%m-%d'))
            notes    = body.get('notes', '').strip()

            if not topic:
                self._send_json({'error': 'Topic name is required'}, 400)
                return

            base = datetime.strptime(date_str, '%Y-%m-%d')
            review_dates = [(base + timedelta(days=d)).strftime('%Y-%m-%d') for d in INTERVALS]

            add_review_to_calendar(topic, category, date_str, notes, review_dates)

            data = load_data()
            # Use max id + 1 to avoid collisions after deletions
            next_id = max((t['id'] for t in data['topics']), default=0) + 1
            entry = {
                'id': next_id,
                'topic': topic,
                'category': category,
                'date_learned': date_str,
                'notes': notes,
                'review_dates': review_dates,
                'created_at': datetime.now().isoformat()
            }
            data['topics'].insert(0, entry)
            save_data(data)
            self._send_json({'success': True, 'entry': entry})

        elif self.path == '/log-revision':
            topic_id         = body.get('id')
            review_date      = body.get('review_date')
            duration_minutes = int(body.get('duration_minutes', 0))

            data = load_data()
            for topic in data['topics']:
                if topic['id'] == topic_id:
                    if 'revisions' not in topic:
                        topic['revisions'] = []
                    # Avoid duplicate entries for same review_date
                    topic['revisions'] = [r for r in topic['revisions'] if r['review_date'] != review_date]
                    topic['revisions'].append({
                        'review_date':      review_date,
                        'revised_at':       datetime.now().isoformat(),
                        'duration_minutes': duration_minutes
                    })
                    save_data(data)
                    self._send_json({'success': True})
                    return
            self._send_json({'error': 'Topic not found'}, 404)

        elif self.path == '/delete-topic':
            topic_id = body.get('id')
            data = load_data()
            data['topics'] = [t for t in data['topics'] if t['id'] != topic_id]
            save_data(data)
            self._send_json({'success': True})

        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, filename, content_type):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self._cors()
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        pass  # silence request logs


if __name__ == '__main__':
    import webbrowser, threading
    print(f"\n Spaced Repetition server running at http://localhost:{PORT}")
    print(" Close this window to stop.\n")
    threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()
    with http.server.HTTPServer(('localhost', PORT), Handler) as httpd:
        httpd.serve_forever()
