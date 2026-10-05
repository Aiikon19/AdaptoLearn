import os

from app import create_app
from scheduler import start_announcements_worker

app = create_app()
if os.environ.get("ANNOUNCEMENT_WORKER", "1") == "1":
    start_announcements_worker(app)

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
