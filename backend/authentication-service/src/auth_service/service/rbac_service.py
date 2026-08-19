"""Role-Based Access Control (RBAC).

Roles group permissions; users are granted roles. The effective permission set
for a user is the union of permissions across all their roles. JWT access tokens
carry both ``realm_access.roles`` and ``permissions`` so downstream services can
enforce without a DB lookup.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.entity.models import Permission, Role, RolePermission, User, UserRole


class RbacService:
    """Queries role/permission assignments and computes effective permissions."""

    # ------------------------------------------------------------ roles

    async def create_role(self, session: AsyncSession, code: str, name: str, description: str | None) -> Role:
        role = Role(code=code, name=name, description=description)
        session.add(role)
        await session.flush()
        return role

    async def get_role(self, session: AsyncSession, code: str) -> Role | None:
        result = await session.execute(select(Role).where(Role.code == code, Role.deleted_at.is_(None)))
        return result.scalar_one_or_none()

    async def list_roles(self, session: AsyncSession) -> list[Role]:
        result = await session.execute(select(Role).where(Role.deleted_at.is_(None)).order_by(Role.code))
        return list(result.scalars().all())

    async def roles_for_user(self, session: AsyncSession, user: User) -> list[Role]:
        result = await session.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, UserRole.deleted_at.is_(None), Role.deleted_at.is_(None))
            .order_by(Role.code)
        )
        return list(result.scalars().all())

    async def assign_roles(self, session: AsyncSession, user: User, role_codes: list[str]) -> list[Role]:
        existing = await self.roles_for_user(session, user)
        existing_codes = {r.code for r in existing}
        for code in role_codes:
            if code in existing_codes:
                continue
            role = await self.get_role(session, code)
            if role is None:
                role = await self.create_role(session, code, code.replace("_", " ").title(), None)
            session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()
        return await self.roles_for_user(session, user)

    async def remove_role_from_user(self, session: AsyncSession, user_id, role_code: str) -> None:
        role = await self.get_role(session, role_code)
        if role is None:
            return
        await session.execute(
            delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )

    # ------------------------------------------------------------ permissions

    async def create_permission(
        self, session: AsyncSession, code: str, resource: str, action: str, description: str | None
    ) -> Permission:
        perm = Permission(code=code, resource=resource, action=action, description=description)
        session.add(perm)
        await session.flush()
        return perm

    async def get_permission(self, session: AsyncSession, code: str) -> Permission | None:
        result = await session.execute(
            select(Permission).where(Permission.code == code, Permission.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_permissions(self, session: AsyncSession) -> list[Permission]:
        result = await session.execute(
            select(Permission).where(Permission.deleted_at.is_(None)).order_by(Permission.code)
        )
        return list(result.scalars().all())

    async def grant_permissions(self, session: AsyncSession, role: Role, permission_codes: list[str]) -> None:
        for code in permission_codes:
            perm = await self.get_permission(session, code)
            if perm is None:
                continue
            exists = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                    RolePermission.deleted_at.is_(None),
                )
            )
            if exists.scalar_one_or_none() is None:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))
        await session.flush()

    async def permissions_for_user(self, session: AsyncSession, user: User) -> list[str]:
        result = await session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user.id,
                UserRole.deleted_at.is_(None),
                RolePermission.deleted_at.is_(None),
                Permission.deleted_at.is_(None),
            )
            .order_by(Permission.code)
        )
        return list(dict.fromkeys(result.scalars().all()))  # de-duplicate preserving order

    async def role_codes_for_user(self, session: AsyncSession, user: User) -> list[str]:
        roles = await self.roles_for_user(session, user)
        return [r.code for r in roles]