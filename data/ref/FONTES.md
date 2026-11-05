# Fontes das tabelas de referência

Arquivos versionados, gerados uma única vez por `scripts/construir_refs.py`. O pipeline e o CI
apenas leem estes arquivos: não há chamada de rede em tempo de execução.

| Arquivo | Conteúdo | Origem | Licença |
|---|---|---|---|
| `municipios.csv` | Código IBGE de 7 dígitos, nome e UF dos 5.571 municípios | [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (`csv/municipios.csv`), compilado a partir dos códigos do IBGE | MIT |
| `uf_malha.geojson` | Contorno das 27 UFs, simplificado (tolerância de 0,08 grau, coordenadas com 2 casas) | Dissolução da malha municipal do IBGE publicada em [tbrugz/geodata-br](https://github.com/tbrugz/geodata-br) (`geojson/geojs-XX-mun.json`) | CC0 1.0 |

**Por que não a API do IBGE diretamente:** o ambiente em que o projeto foi construído não tinha
acesso a `servicodados.ibge.gov.br`. As duas fontes acima redistribuem dados do IBGE e têm licença
aberta. Para atualizar a partir do IBGE, basta trocar as entradas do script pela malha de UFs e pela
lista de municípios do serviço de dados do IBGE.

**Uso:** os códigos servem para validar os relatos (regras V03 e V04) e a malha para o mapa do
relatório. Nenhum dado de pessoas vem destas fontes.
