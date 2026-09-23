# Backups e preservação

Mantenha backups do banco PostgreSQL e do volume que armazena o corpus. Use
procedimentos compatíveis com a infraestrutura local e verifique restauração em
ambiente separado antes de depender de um backup.

Não apague volumes como estratégia normal de recuperação. Snapshots congelados,
versões anteriores e o runtime ativo são parte da rastreabilidade. O banco de
testes é separado e não substitui um backup operacional.
