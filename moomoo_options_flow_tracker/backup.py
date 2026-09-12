from pathlib import Path
from datetime import datetime
import shutil

def backup_database(db_path):
    src = Path(db_path)
    if not src.exists():
        return None
    out = Path("backups")
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dest = out / f"options_flow_{stamp}.db"
    shutil.copy2(src, dest)
    return str(dest)
