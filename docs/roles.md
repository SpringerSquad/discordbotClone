# Role management

The project defines all role names in `utils/auth.py` to keep authorization
logic consistent.  Available roles are exposed as constants such as
`ROLE_ADMIN` and `ROLE_SUPPORT`.

## Adding or changing roles

1. Define a new constant in [`utils/auth.py`](../utils/auth.py).
2. Add the role to `models.RoleEnum` so it can be stored in the database.
3. Update routes and templates that use `require_role` or reference role names.
4. Adjust any settings files or seed data that rely on role strings.

Managing roles in this single location makes future changes straightforward and
avoids hard‑coded strings scattered throughout the codebase.