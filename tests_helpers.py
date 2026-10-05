def token(client):
    return {"X-CSRF-Token": client.get("/api/bootstrap").json["csrf"]}


def send(client, path, method="POST", data=None):
    if path == "login" and data and "role" not in data:
        data = {**data, "role": "student"}
    return client.open("/api/" + path, method=method, json=data or {}, headers=token(client))


def registration(**changes):
    return {
        "name": "Student",
        "email": "221234567@dut4life.ac.za",
        "password": "StudentPassword123",
        "institution_id": 3,
        "programme": "BSc Computer Science",
        "year": 2,
        **changes,
    }
