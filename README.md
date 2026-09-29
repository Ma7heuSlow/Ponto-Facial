# Ponto Facial

Sistema desktop de controle de ponto por reconhecimento facial, desenvolvido em Python com OpenCV. É uma alternativa prática e segura aos métodos tradicionais de registro de jornada.

## Funcionalidades

- **Reconhecimento facial em tempo real** com os modelos YuNet (detecção) e SFace (reconhecimento) do OpenCV
- **Prova de vida:** pede que a pessoa vire o rosto, o que dificulta fraude com fotos
- **Registro automático da jornada:** entrada, saída para almoço, volta do almoço e saída
- **Câmera flexível:** webcam do PC ou câmera do celular pela rede (DroidCam, Iriun, IP Webcam)
- **Relatórios em Excel** com cálculo de horas trabalhadas
- **Painel administrativo** protegido por senha
- **LGPD:** dados biométricos armazenados apenas localmente, com consentimento e exclusão no desligamento

## Tecnologias

Python · OpenCV · SQLite · CustomTkinter/Tkinter · Pandas · OpenPyXL

## Como executar

Requisitos: Python 3.10 ou superior.

```bash
pip install -r requirements.txt
python ponto.py
```

No Windows, também dá para abrir pelo `iniciar.bat`.

Na primeira execução, o programa baixa os modelos do [OpenCV Zoo](https://github.com/opencv/opencv_zoo) para a pasta `modelos/` e cria o arquivo `config.json` com as configurações padrão.

## Configuração

Em **Configurações** (senha padrão do administrador: `1234`, troque no primeiro uso) é possível ajustar:

| Opção | Descrição |
|---|---|
| Câmera | `0` para a webcam do PC, `1`, `2`... para outras câmeras, ou uma URL como `http://IP-DO-CELULAR:4747/video` |
| Espelhar | Espelha a imagem da câmera |
| Prova de vida | Liga ou desliga a verificação de movimento do rosto |
| Limiar | Semelhança mínima para reconhecer (0 a 1; quanto maior, mais rigoroso) |
| Intervalo mínimo | Minutos mínimos entre duas batidas da mesma pessoa |

## Privacidade

Os dados biométricos e os registros de ponto ficam somente na máquina local (`dados/ponto.db`) e **não fazem parte deste repositório**.

## Autor

**Matheus Henrique**, estudante de Análise e Desenvolvimento de Sistemas no Centro Universitário Estácio de Brasília
[LinkedIn](https://www.linkedin.com/in/matheus-henrique-444992322) · [GitHub](https://github.com/Ma7heuSlow)
