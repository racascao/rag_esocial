# Atualização de versão

1. O runtime atual permanece ativo.
2. O operador informa URLs do MOS, XSD e Leiaute principal.
3. Os anexos são descobertos e os arquivos são baixados e validados.
4. O sistema cria snapshot, build, materializações e projeções.
5. Após readiness, o runtime é ativado atomicamente.

Em qualquer falha antes da ativação, a cadeia anterior continua disponível. Não
há troca parcial nem URL de versão hardcoded. Consulte também
[UX operacional](../operational_ux.md).
