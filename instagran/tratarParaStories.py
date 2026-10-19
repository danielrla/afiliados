#!/usr/bin/env python3
"""Compatibilidade com tratarParaStories: redireciona para instagran.tratarParaInstagran."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from instagran.tratarParaInstagran import (
    fetch_product_info,
    render_story_image,
    render_template_to_image,
    gerar_todas_imagens,
    gerar_codigo_unico,
    main,
)

if __name__ == "__main__":
    main()
