# ADR 0004 — Regra global e provedor de classificação intercambiável

## Contexto

O produto precisa de uma única regra editável, sem versionamento nem múltiplos
rulesets. O ambiente local e os testes não podem depender de chave, custo ou
latência de um LLM externo. A saída precisa ser JSON estrito e validada.

## Decisão

Persistir uma única linha em `classification_rule` com o prompt global. Cada
análise copia o prompt no momento da criação (`rule_prompt`), então edições
posteriores não alteram trabalho já enfileirado.

Definir `RelevanceProvider` no domínio com `classify`. A implementação padrão é
`HeuristicRelevanceProvider`, determinística e baseada em palavras-chave do
prompt. `OpenAiCompatibleProvider` usa HTTP compatível com a API OpenAI, sem SDK,
e é habilitado por `LLM_PROVIDER=openai`.

Toda resposta passa por `AnalysisResult`: uma das três classes públicas, resumo
de 1 a 280 caracteres e justificativa de 1 a 1000 caracteres. Saída inválida
dispara uma única correção; se falhar de novo, a análise é marcada como falha
permanente. Conteúdo de entrada vai em bloco delimitado como material não
confiável; regra e schema ficam em blocos separados para reduzir prompt
injection.

## Consequências

- Desenvolvimento e CI rodam sem rede e sem custo.
- A heurística não substitui avaliação de qualidade de um LLM real.
- O prompt é um contrato operacional: mudanças afetam apenas análises futuras.
