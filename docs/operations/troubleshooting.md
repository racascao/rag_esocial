# Troubleshooting

| Sintoma | Ação segura |
| --- | --- |
| Docker indisponível | Inicie o daemon Docker e execute `./esocial` novamente. |
| Primeira execução pede URLs | Informe MOS, pacote XSD e Leiaute oficial. |
| Ausência de evidência | Reformule com evento/nome técnico; não é erro técnico. |
| Atualização falhou | Consulte Status: o runtime anterior deve permanecer ativo. |
| Banco não sobe | Verifique `docker compose ps` e `docker compose logs db`. |

Não apague volumes ou snapshots para “forçar” recuperação sem backup validado.
