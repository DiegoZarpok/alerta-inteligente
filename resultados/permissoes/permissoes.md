# Teste de permissões (05/11/2026 11:30)

296 de 296 operações tiveram o resultado esperado.

| Usuário | Alvo | Operação | Esperado | Obtido | Confere | DENY previsto |
|---|---|---|---|---|---|---|
| svc_coleta | series_hidrologicas | find | permitido | permitido | sim |  |
| svc_coleta | series_hidrologicas | insert | permitido | permitido | sim |  |
| svc_coleta | estacoes | find | permitido | permitido | sim |  |
| svc_coleta | auditoria | insert | permitido | permitido | sim |  |
| svc_modelo | series_hidrologicas | find | permitido | permitido | sim |  |
| svc_modelo | estacoes | find | permitido | permitido | sim |  |
| svc_modelo | previsoes | find | permitido | permitido | sim |  |
| svc_modelo | previsoes | insert | permitido | permitido | sim |  |
| svc_modelo | auditoria | insert | permitido | permitido | sim |  |
| svc_ia | previsoes | find | permitido | permitido | sim |  |
| svc_ia | alertas | insert | permitido | permitido | sim |  |
| svc_ia | documentos | find | permitido | permitido | sim |  |
| svc_ia | moradores | find | negado | negado | sim | sim |
| svc_ia | relatos | find | negado | negado | sim | sim |
| svc_ia | auditoria | insert | permitido | permitido | sim |  |
| svc_ia | auditoria | remove | negado | negado | sim | sim |
| svc_ia | admin | grantRolesToUser | negado | negado | sim | sim |
| svc_classificador | relatos | update | permitido | permitido | sim |  |
| svc_classificador | auditoria | insert | permitido | permitido | sim |  |
| svc_classificador | vw_relatos_anonimizados | find | permitido | permitido | sim |  |
| svc_bot | alertas | find | permitido | permitido | sim |  |
| svc_bot | moradores | find | permitido | permitido | sim |  |
| svc_bot | moradores | insert | permitido | permitido | sim |  |
| svc_bot | moradores | update | permitido | permitido | sim |  |
| svc_bot | moradores | remove | permitido | permitido | sim |  |
| svc_bot | relatos | insert | permitido | permitido | sim |  |
| svc_bot | relatos | remove | permitido | permitido | sim |  |
| svc_bot | auditoria | insert | permitido | permitido | sim |  |
| svc_n8n | auditoria | insert | permitido | permitido | sim |  |
| operador_defesa_civil | series_hidrologicas | find | permitido | permitido | sim |  |
| operador_defesa_civil | estacoes | find | permitido | permitido | sim |  |
| operador_defesa_civil | previsoes | find | permitido | permitido | sim |  |
| operador_defesa_civil | alertas | find | permitido | permitido | sim |  |
| operador_defesa_civil | moradores | find | negado | negado | sim | sim |
| operador_defesa_civil | relatos | find | negado | negado | sim | sim |
| operador_defesa_civil | auditoria | remove | negado | negado | sim | sim |
| operador_defesa_civil | vw_moradores_mascarado | find | permitido | permitido | sim |  |
| operador_defesa_civil | vw_relatos_anonimizados | find | permitido | permitido | sim |  |
| operador_defesa_civil | admin | grantRolesToUser | negado | negado | sim | sim |
| auditor | alertas | find | permitido | permitido | sim |  |
| auditor | auditoria | remove | negado | negado | sim | sim |
| auditor | vw_auditoria_mascarada | find | permitido | permitido | sim |  |

A tabela mostra todas as permissões concedidas, os DENY previstos na Entrega 1 e qualquer divergência. A lista completa, com as demais negações, está em permissoes.json.