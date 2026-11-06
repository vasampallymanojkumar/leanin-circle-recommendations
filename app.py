"""Run with python app.py; standard-library HTTP server for local evaluation."""
import argparse
import json
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit
from recommender import SNAPSHOT_DATE, connect, recommend, seed


def make_handler(db, as_of):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path)
            parts = path.path.strip('/').split('/')
            if path.path == '/health':
                return self.send_json(200, {'status': 'ok', 'as_of': as_of})
            if len(parts) != 3 or parts[0] != 'users' or parts[2] != 'recommendations':
                return self.send_json(404, {'error': 'Route not found'})
            try:
                query = parse_qs(path.query, keep_blank_values=True)
                if set(query) - {'limit'} or len(query.get('limit', [])) > 1:
                    raise ValueError('Use only one optional limit parameter')
                if not parts[1].isascii() or not parts[1].isdigit() or int(parts[1]) < 1:
                    raise ValueError('user_id must be a positive integer')
                raw_limit = query.get('limit', ['5'])[0]
                if not raw_limit.isascii() or not raw_limit.isdigit():
                    raise ValueError('limit must be an integer from 1 to 20')
                result = recommend(db, int(parts[1]), int(raw_limit), as_of)
                self.send_json(200, result)
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)})
            except LookupError as exc:
                self.send_json(404, {'error': str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default='circles.sqlite3')
    parser.add_argument('--as-of', default=SNAPSHOT_DATE, type=lambda s: date.fromisoformat(s).isoformat())
    args = parser.parse_args()
    db = connect(args.db)
    seed(db)
    server = HTTPServer(('127.0.0.1', args.port), make_handler(db, args.as_of))
    print(f'Listening on http://127.0.0.1:{args.port}; reference date {args.as_of}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        db.close()


if __name__ == '__main__':
    main()
