# Início rápido

O fluxo normal exige Docker e Docker Compose com o daemon em execução. Python,
`uv`, PostgreSQL e Ollama não precisam estar instalados no host.

```sh
cd rag_esocial
./esocial
```

O launcher constrói os serviços, aguarda o banco, aplica migrations e abre o
menu. Na primeira execução, informe URLs oficiais do MOS, pacote XSD e Leiaute
principal. O projeto não fixa URLs: use as referências oficiais da versão que
será importada.

!!! note
    Consultas de evidência no menu normal não dependem de Ollama. Os recursos
    de Answer Contract e avaliação têm contratos e comandos próprios.
