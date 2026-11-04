# ADR 0003 — Docling, texto direto e links com httpx/parsel

## Contexto

PDFs, DOCX, PPTX, imagens, áudio e vídeo exigem conversão pesada e nem sempre
estão disponíveis no ambiente de testes. Texto e Markdown não precisam de
OCR/conversão. Scrapy tem um reactor próprio, difícil de compartilhar com o
event loop do FastAPI/Celery.

## Decisão

- Docling é o conversor principal e fica atrás de `DocumentConverter`, instalado
  no extra `docling` (com `docling[asr]` para áudio/vídeo) e na imagem Docker.
- Texto e Markdown são normalizados diretamente, sem passar por Docling. O mesmo
  vale para arquivos `.txt`/`.md` enviados por upload.
- Links são buscados com `httpx.AsyncClient`, com redirects manuais e validação
  SSRF em cada salto. `parsel` seleciona o conteúdo principal e os metadados
  antes da conversão para Markdown.
- Testes unitários usam conversores e fetchers fake; Docling real não é
  obrigatório no host.

## Consequências

- Não há subprocesso Scrapy nem worker separado de crawl.
- Formatos sem conversor retornam falha permanente clara.
- A imagem Docker é maior por causa de Docling/PyTorch/FFmpeg.
