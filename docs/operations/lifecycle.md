# Ciclo de vida operacional

```mermaid
flowchart LR
    A[Runtime ativo] --> B{Nova versão?}
    B -- Não --> A
    B -- Sim --> C[Validação e novo snapshot]
    C --> D[Build e índices]
    D --> E{Readiness?}
    E -- Sim --> F[Ativação atômica]
    E -- Não --> A
```

Uma versão oficial nova é diferente de uma revisão de parser e de uma revisão
de search. O runtime só muda após preparação completa. Snapshots congelados não
são alterados.
