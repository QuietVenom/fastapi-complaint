from schemas.base import BaseUser

class UserRegisterIn(BaseUser):
    password: str
    phone_number: str
    first_name: str
    last_name: str
    iban: str


class UserLoginIn(BaseUser):
    password: str
