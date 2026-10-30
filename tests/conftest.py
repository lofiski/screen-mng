import os
import tempfile

os.environ["SCREEN_MNG_HOME"] = tempfile.mkdtemp(prefix="screen_mng_test_")

from screen_mng import win32  # noqa: E402

win32.set_dpi_aware()
