# Netzwerkkontrolle 4.1

[English](../README.md) · [Español](../LEEME.md) · [Français](README.fr.md) · [简体中文](README.zh.md) · [Português](README.pt.md) · [Русский](README.ru.md)

Lokales Windows-Dashboard zum Erkennen von Netzwerkgeräten, Anzeigen des Herstellers anhand der MAC-Adresse und Verwalten des Zugriffs.

## Starten

1. Installiere [Npcap](https://npcap.com/#download).
2. Beende eine ältere Programmversion über **Beenden**.
3. Starte **ControlRed-v4.1.exe**, bei Bedarf als Administrator.
4. Wähle einen physischen Ethernet- oder WLAN-Adapter.
5. Wähle oben in der Sprachleiste **Deutsch**.

Die Sprache wird im Browser gespeichert. Eigene Gerätenamen und gespeicherte Berechtigungen bleiben erhalten. Demostracion.cmd startet eine simulierte Umgebung.

## Zugriff verwalten

Im Modus **Manuelle Sperren** wählst du die Geräte einzeln. Im Modus **Freigabeliste** wird für jedes erkannte Gerät ohne Berechtigung eine Sperre angefordert. Mit **Zulassen** oder **MAC-Adresse freigeben** erteilst du Berechtigungen. Router und eigener PC sind geschützt.

Lass diesen PC und das Programm laufen; du kannst den Tab schließen. Sperren bleiben aktiv, bis du sie aufhebst oder das Programm beendest. Für IPv6 müssen Adressen und Router erkannt werden. Schutzfunktionen im Netzwerk können Sperren einschränken.

Beim Start erfolgt eine Suche; danach nutzt du Netzwerk aktualisieren. Die Kontrolle läuft ohne regelmäßige Suchläufe weiter. Neue Geräte können durch beobachteten lokalen Verkehr erscheinen; aktualisiere das Netzwerk, wenn ein Gerät fehlt.

Die Wirksamkeit hängt vom Netzwerk und den Schutzfunktionen der Geräte ab. Ein angeforderter Block ist kein Nachweis einer unterbrochenen Internetverbindung. Verwende das Programm nur in Netzwerken, die du verwalten darfst.

Hinweise zu Quellcode, Tests und Builds stehen in der [englischen README](../README.md).
