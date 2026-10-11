r"""Create an admin account (e.g. the first super admin) from the command line.

    cd backend; .venv\Scripts\activate
    python -m app.scripts.create_admin --name "Full Name" --email you@example.com
    python -m app.scripts.create_admin --name "..." --email ... --role clinic_manager --clinic-id 3

The password is typed twice without being shown, so it never appears on screen, in the shell
history or in any file.
"""

import argparse
import getpass
import sys
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Admin
from app.models.choices import ADMIN_ROLES
from app.repositories import admin_repository
from app.schemas.auth import FullName, NewEmail, NewPassword

# stricter than the 8 required for app users: an admin account can change rules and see all
# appointments
ADMIN_PASSWORD_MIN_LENGTH = 12


class NewAdmin(BaseModel):
    full_name: FullName
    email: NewEmail
    password: Annotated[NewPassword, Field(min_length=ADMIN_PASSWORD_MIN_LENGTH)]
    role: str = "super_admin"
    clinic_id: int | None = None

    @field_validator("role")
    @classmethod
    def known_role(cls, value: str) -> str:
        if value not in ADMIN_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ADMIN_ROLES)}")
        return value

    @model_validator(mode="after")
    def clinic_only_for_managers(self) -> "NewAdmin":
        # same rule as the admins table CHECK constraint, with a readable message
        if (self.role == "clinic_manager") != (self.clinic_id is not None):
            raise ValueError("A clinic id is required for clinic managers and only for them")
        return self


class AdminCreationError(Exception):
    pass


def create_admin(db: Session, data: NewAdmin) -> Admin:
    if admin_repository.get_by_email(db, data.email) is not None:
        raise AdminCreationError(f"An admin with the email {data.email} already exists")
    try:
        admin = admin_repository.create(
            db,
            full_name=data.full_name,
            email=data.email,
            password_hash=hash_password(data.password),
            role=data.role,
            clinic_id=data.clinic_id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AdminCreationError("Could not create the admin (does the clinic exist?)") from None
    return admin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an admin account.")
    parser.add_argument("--name", required=True, help="full name")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", default="super_admin", choices=ADMIN_ROLES)
    parser.add_argument("--clinic-id", type=int, help="required for clinic_manager")
    args = parser.parse_args(argv)

    password = getpass.getpass(f"Password (at least {ADMIN_PASSWORD_MIN_LENGTH} characters): ")
    if getpass.getpass("Repeat the password: ") != password:
        print("The passwords do not match.", file=sys.stderr)
        return 1

    try:
        data = NewAdmin(
            full_name=args.name,
            email=args.email,
            password=password,
            role=args.role,
            clinic_id=args.clinic_id,
        )
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"]) or "input"
            print(f"{field}: {error['msg']}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            admin = create_admin(db, data)
        except AdminCreationError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Created {admin.role} #{admin.id}: {admin.full_name} <{admin.email}>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
