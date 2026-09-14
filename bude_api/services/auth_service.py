"""Authentication service — wraps Frappe's built-in login/session APIs.

Returns API key/secret pairs so the mobile client can authenticate subsequent
requests via `Authorization: token <key>:<secret>` without storing passwords.
"""


try:
    import frappe
    from frappe.utils.password import update_password
except ImportError:
    frappe = None
    update_password = None


class AuthError(Exception):
    pass


def default_warehouse_for(user: str) -> str:
    """`default_warehouse` is a custom User field that only exists on
    RFID-inventory sites; HR-only sites must not crash on login without it."""
    if frappe is None:
        return ""
    if not frappe.get_meta("User").has_field("default_warehouse"):
        return ""
    return frappe.db.get_value("User", user, "default_warehouse") or ""


class AuthService:
    def login(self, username: str, password: str) -> dict:
        """Authenticate against Frappe and return a session dict.

        Returns: {
            "user": str,
            "full_name": str,
            "api_key": str,
            "api_secret": str,
            "roles": list[str],
            "default_warehouse": str,
        }
        """
        if frappe is None:
            raise RuntimeError("Frappe is not available — run inside a Frappe bench.")

        login_manager = frappe.auth.LoginManager()
        try:
            login_manager.authenticate(user=username, pwd=password)
            login_manager.post_login()
        except frappe.AuthenticationError as exc:
            raise AuthError("Invalid username or password.") from exc

        user_name = frappe.session.user
        user_doc = frappe.get_doc("User", user_name)

        api_key, api_secret = self._ensure_api_keys(user_doc)

        return {
            "user": user_name,
            "full_name": user_doc.full_name,
            "api_key": api_key,
            "api_secret": api_secret,
            "roles": frappe.get_roles(user_name),
            "default_warehouse": default_warehouse_for(user_name),
        }

    def google_config(self) -> dict:
        """Whether Google sign-in is available, and the client id the app must
        sign against. Reuses this ERPNext site's Google Social Login Key so no
        separate OAuth client is needed."""
        client_id = self._google_client_id()
        return {"enabled": bool(client_id), "client_id": client_id}

    def login_with_google(self, id_token: str) -> dict:
        """Verify a Google ID token and return the same session dict as
        password login. Existing, enabled ERPNext users only — never creates a
        user, and never trusts the client's claimed identity."""
        if frappe is None:
            raise RuntimeError("Frappe is not available — run inside a Frappe bench.")
        client_id = self._google_client_id()
        if not client_id:
            raise AuthError("Google sign-in is not configured on this server.")

        email = self._verify_google_token(id_token, client_id)
        user_name = frappe.db.get_value("User", {"email": email, "enabled": 1}, "name")
        if not user_name:
            raise AuthError("No active ERPNext account is linked to this Google account.")

        user_doc = frappe.get_doc("User", user_name)
        api_key, api_secret = self._ensure_api_keys(user_doc)
        return {
            "user": user_name,
            "full_name": user_doc.full_name,
            "api_key": api_key,
            "api_secret": api_secret,
            "roles": frappe.get_roles(user_name),
            "default_warehouse": default_warehouse_for(user_name),
        }

    def _google_client_id(self) -> str | None:
        if frappe is None:
            return None
        # Frappe installations in the wild use both `google` and `Google` as
        # the Social Login Key document name. Desk login resolves providers
        # case-insensitively, so the mobile endpoint must do the same.
        for key_name in ("google", "Google"):
            row = frappe.db.get_value(
                "Social Login Key",
                key_name,
                ["client_id", "enable_social_login"],
                as_dict=True,
            )
            if row and row.get("enable_social_login") and row.get("client_id"):
                return row.get("client_id")
        return None

    def _verify_google_token(self, id_token: str, client_id: str) -> str:
        """Server-side verification of a Google ID token. Returns the verified
        email, or raises AuthError. Checks signature (Google's public keys),
        audience, issuer, and that the email is verified."""
        import jwt
        from jwt import PyJWKClient

        try:
            jwks = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
            signing_key = jwks.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=client_id,
            )
        except Exception as exc:  # noqa: BLE001 - any failure means untrusted
            raise AuthError("Could not verify the Google sign-in.") from exc

        if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
            raise AuthError("Unexpected Google token issuer.")
        email = claims.get("email")
        if not email or not claims.get("email_verified"):
            raise AuthError("This Google account has no verified email.")
        return email

    def logout(self) -> None:
        if frappe is None:
            raise RuntimeError("Frappe is not available — run inside a Frappe bench.")
        frappe.local.login_manager.logout()
        frappe.db.commit()

    def current_user(self) -> str | None:
        if frappe is None:
            return None
        user = getattr(frappe.session, "user", None)
        if user in (None, "Guest"):
            return None
        return user

    def _ensure_api_keys(self, user_doc) -> tuple[str, str]:
        api_key = user_doc.api_key
        api_secret = user_doc.get_password("api_secret", raise_exception=False) if api_key else None

        if not api_key or not api_secret:
            if not api_key:
                api_key = frappe.generate_hash(length=15)
                user_doc.api_key = api_key
            api_secret = frappe.generate_hash(length=15)
            user_doc.api_secret = api_secret
            user_doc.save(ignore_permissions=True)
            frappe.db.commit()

        return api_key, api_secret
