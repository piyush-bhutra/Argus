import logging
import os
from app.core.config import settings

def setup_logging():
    if not os.path.exists(settings.log_dir):
        os.makedirs(settings.log_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(f"{settings.log_dir}/app.log"),
            logging.StreamHandler()
        ]
    )

logger = logging.getLogger("argus")
