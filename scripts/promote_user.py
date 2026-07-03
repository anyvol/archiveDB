#!/usr/bin/env python3
"""Assign admin or reviewer role to an existing user (manual DB promotion)."""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.future import select

from app.database import async_session
from app.models import User, UserRole


async def promote(login: str, role: str) -> None:
    role_enum = UserRole(role)
    async with async_session() as session:
        result = await session.execute(select(User).where(User.login == login))
        user = result.scalars().first()
        if not user:
            print(f"User '{login}' not found.")
            sys.exit(1)
        user.role = role_enum
        await session.commit()
        print(f"User '{login}' role set to '{role_enum.value}'.")


def main():
    parser = argparse.ArgumentParser(description="Promote user role in archiveDB")
    parser.add_argument("login", help="User login")
    parser.add_argument(
        "role",
        choices=[
            UserRole.master_admin.value,
            UserRole.admin.value,
            UserRole.reviewer.value,
            UserRole.user.value,
        ],
        help="New role",
    )
    args = parser.parse_args()
    asyncio.run(promote(args.login, args.role))


if __name__ == "__main__":
    main()
