"""SSH + WP-CLI executor for WP Site Connector.

Connects to WordPress servers via SSH and runs wp-cli commands to retrieve
data not available through the REST API (PHP version, update counts, cron
jobs, database size, etc.).
"""
import asyncio
import json

try:
    import asyncssh
    _ASYNCSSH_AVAILABLE = True
except ImportError:
    _ASYNCSSH_AVAILABLE = False

_CMD_TIMEOUT = 30  # seconds per WP-CLI command


def _connect_kwargs(cred: dict) -> dict:
    kwargs = dict(
        host=cred["host"],
        port=int(cred.get("port", 22)),
        username=cred["user"],
        known_hosts=None,  # skip host-key verification — trade-off for ease of setup
    )
    if cred.get("key"):
        kwargs["client_keys"] = [asyncssh.import_private_key(cred["key"])]
    elif cred.get("password"):
        kwargs["password"] = cred["password"]
    else:
        raise ValueError("SSH credentials must include either key or password.")
    return kwargs


async def _run(conn, cmd: str, wp_path: str) -> str | None:
    """Run one WP-CLI command; return stdout or None on failure/timeout."""
    full = f"wp {cmd} --path={wp_path} --allow-root"
    try:
        r = await asyncio.wait_for(conn.run(full, check=False), timeout=_CMD_TIMEOUT)
        return r.stdout.strip() if r.exit_status == 0 else None
    except (asyncio.TimeoutError, Exception):
        return None


async def test_connection(cred: dict) -> tuple[bool, str]:
    """Test SSH connection and verify WP-CLI works. Returns (ok, message)."""
    if not _ASYNCSSH_AVAILABLE:
        return False, "asyncssh is not installed — add it to pyproject.toml dependencies."
    wp_path = cred.get("wp_path", "/var/www/html")
    try:
        async with asyncssh.connect(**_connect_kwargs(cred)) as conn:
            version = await _run(conn, "core version", wp_path)
            if version is None:
                return False, f"WP-CLI not found or WordPress not at {wp_path}"
            return True, f"WordPress {version}"
    except asyncssh.PermissionDenied:
        return False, "SSH permission denied — check username and key/password."
    except (OSError, ConnectionRefusedError):
        return False, f"Cannot connect to {cred['host']}:{cred.get('port', 22)}"
    except Exception as e:
        return False, str(e)[:200]


async def get_server_info(cred: dict) -> dict:
    """Run WP-CLI commands and return a dict of server/site information."""
    if not _ASYNCSSH_AVAILABLE:
        return {"error": "asyncssh not installed"}
    wp_path = cred.get("wp_path", "/var/www/html")
    try:
        async with asyncssh.connect(**_connect_kwargs(cred)) as conn:
            (wp_ver, php_ver, plugin_upd, theme_upd,
             core_upd, cron_cnt, db_size) = await asyncio.gather(
                _run(conn, "core version", wp_path),
                _run(conn, "eval 'echo PHP_VERSION;'", wp_path),
                _run(conn, "plugin list --update=available --format=count", wp_path),
                _run(conn, "theme list --update=available --format=count", wp_path),
                _run(conn, "core check-update --format=json", wp_path),
                _run(conn, "cron event list --format=count", wp_path),
                _run(conn, "db size --size_format=mb", wp_path),
            )
    except Exception as e:
        return {"error": str(e)[:200]}

    # Parse core update
    core_update = False
    core_update_ver = ""
    if core_upd:
        try:
            updates = json.loads(core_upd)
            if updates and isinstance(updates, list):
                core_update = True
                core_update_ver = updates[0].get("version", "")
        except Exception:
            pass

    def _int(val):
        return int(val) if val and str(val).strip().isdigit() else 0

    return {
        "wp_version":         wp_ver or "",
        "php_version":        php_ver or "",
        "plugin_updates":     _int(plugin_upd),
        "theme_updates":      _int(theme_upd),
        "core_update":        core_update,
        "core_update_version": core_update_ver,
        "cron_count":         _int(cron_cnt),
        "db_size_mb":         db_size or "",
    }
