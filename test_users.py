"""TEST USERS ONLY — do not use in production.

Server-side configuration used only by the explicit development seed command.
"""

from typing import Literal, TypedDict

__test__ = False


class TestUser(TypedDict):
    email: str
    password: str
    role: Literal["admin"]
    firstName: str
    lastName: str
    isTestUser: Literal[True]


TEST_USERS: tuple[TestUser, ...] = (
    {
        "email": "22445780@dut4life.ac.za",
        "password": "admin@1234",
        "role": "admin",
        "firstName": "DUT",
        "lastName": "Admin",
        "isTestUser": True,
    },
)
