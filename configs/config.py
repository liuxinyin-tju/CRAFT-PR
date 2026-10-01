import os
import sys

import tree_sitter_java as tsjava

from pathlib import Path
from tree_sitter import Language

JAVA_LANGUAGE = Language(tsjava.language(), name='java')

PROJECT_BASE = Path(__file__).parent.parent
