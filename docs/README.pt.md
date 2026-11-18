# Controle de rede 4.1

[English](../README.md) · [Español](../LEEME.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [简体中文](README.zh.md) · [Русский](README.ru.md)

Painel local para Windows que detecta dispositivos, identifica fabricantes pelo endereço MAC e gerencia o acesso à rede.

## Como abrir

1. Instale o [Npcap](https://npcap.com/#download).
2. Feche a versão anterior com **Sair**.
3. Abra **ControlRed-v4.1.exe**, como administrador se necessário.
4. Selecione o adaptador Ethernet ou Wi-Fi físico.
5. Escolha **Português** na barra de idiomas no topo do painel.

O idioma fica salvo no navegador. Nomes personalizados e permissões são preservados. Demostracion.cmd abre um ambiente simulado.

## Gerenciar acesso

No **Bloqueio manual**, você escolhe os dispositivos individualmente. Na **Lista de permissões**, o bloqueio é solicitado para cada dispositivo detectado sem autorização. Use **Permitir** ou **Adicionar MAC permitida** para autorizar dispositivos. O roteador e este PC ficam protegidos.

Mantenha este PC e o programa ligados; você pode fechar a aba. Os bloqueios continuam até você desativá-los ou sair do programa. IPv6 exige detectar os endereços e o roteador. As proteções da rede podem limitar o bloqueio.

Uma busca ao iniciar; depois, use Atualizar rede. O controle continua sem buscas periódicas. Novos dispositivos podem aparecer pelo tráfego local observado; atualize a rede se algum dispositivo não aparecer.

O resultado depende da rede e das proteções dos dispositivos. Uma solicitação de bloqueio não comprova que a conexão à internet foi interrompida. Use o programa apenas em redes que você tem autorização para administrar.

Consulte o [README em inglês](../README.md) para o código-fonte, testes e compilação.
