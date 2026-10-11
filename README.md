# FloGrappling Downloader

Programma con interfaccia grafica per scaricare più video di FloGrappling in una volta sola, a partire da una lista di link.

## Cosa fa

* Scarica più video contemporaneamente (da 1 a 8 download in parallelo).
* Accetta i link delle pagine evento (`...videos?playing=ID`, anche con `\&search=...`), i link `/video/ID-nome` o il solo ID numerico.
* Salva ogni video con il suo titolo, ad esempio `Nome Atleta vs Nome Atleta 2026 Evento.mp4`. Se il titolo non è disponibile usa l'ID.
* Mostra stato e percentuale di ogni download, con un riepilogo finale.
* Salta i video già presenti nella cartella, quindi puoi rilanciare la stessa lista senza riscaricare tutto.
* Scarica nella qualità migliore disponibile, senza ricodificare il video.
* Avvisa se un file ha l'audio assente o quasi muto.

## Requisiti

|Cosa|Come installarlo|
|-|-|
|Python 3.8 o successivo|[python.org](https://www.python.org/downloads/). Durante l'installazione spunta **Add python.exe to PATH**|
|ffmpeg|`winget install Gyan.FFmpeg`, poi chiudi e riapri il terminale|
|Libreria `requests`|`pip install -r requirements.txt` (se manca, il programma prova a installarla da solo)|

L'interfaccia grafica usa `tkinter`, già incluso nell'installazione standard di Python per Windows.

Per verificare che tutto sia a posto:

```
python --version
ffmpeg -version
```

## Installazione

1. Scarica o copia in una cartella questi file: `flo\_downloader.py`, `requirements.txt`, `avvia.bat`.
2. Apri un terminale in quella cartella e installa la dipendenza:

```
   pip install -r requirements.txt
   ```

## Uso

Avvia il programma con un doppio clic su `avvia.bat`, oppure da terminale:

```
python flo\_downloader.py
```

Vai sul link di flograppling della gara interessata, esempio: https://www.flograppling.com/events/15272371-2026-uijj-adriatico-bjj-cup


Cerca il video che vuoi, per cognome, esempio:

https://www.flograppling.com/events/15272371-2026-uijj-adriatico-bjj-cup/videos?playing=16236677\&search=de%20nuccio





Poi:

1. Incolla i link nella casella in alto, uno per riga (premere invio prima di incollarne un altro).
2. Scegli la cartella di destinazione (di default `Download`).
3. Imposta quanti download far partire insieme. Il valore predefinito è 3: se la connessione è lenta, abbassalo. In ogni caso si metteranno in coda, non è un hard limit, appena finito uno paassa all'altro.
4. Premi **Avvia download**.

**Ferma tutto** interrompe i download in corso e cancella i file incompleti. **Apri cartella** apre la cartella di destinazione.

## Note

* Durante il download il file ha estensione `.part.mp4`. Viene rinominato solo a download completato.
* Se un video ha già lo stesso nome nella cartella, viene saltato (`Già presente`). Per riscaricarlo, cancella o sposta il vecchio file.
* Se due video hanno lo stesso titolo, il secondo viene saltato per lo stesso motivo.
* Alcuni video, ad esempio le riprese dei tappeti, possono non avere audio nella sorgente. In quel caso lo stato mostra `Completato (audio quasi muto...)` o `Completato (senza audio)`: il file è identico a quello che fornisce il server, non ho trovato un modo per ottenerne una copia buona, sempre che esista.
* Le dirette in corso non hanno una durata fissa: il download non mostra la percentuale e continua finché la diretta non termina.

## Problemi comuni

**La finestra non si apre, o si chiude subito.**
Avvia con `avvia.bat` o da PowerShell con `python flo\_downloader.py`, così vedi l'eventuale errore. Controlla anche che Python sia nel PATH.

**Compare l'avviso "ffmpeg mancante".**
Installa ffmpeg con `winget install Gyan.FFmpeg`, poi chiudi e riapri il programma. Windows aggiorna il PATH solo per i nuovi avvii.

**Un video dà errore "Nessun video disponibile".**
L'ID potrebbe essere sbagliato, oppure il video è cryptato in qualche modo che per ora non ho incontrato.

**Il file si chiama solo con un numero (l'ID).**
Il programma non è riuscito a leggere il titolo. Il motivo compare nella colonna Stato (`titolo non letto: ...`).

**L'errore `parse\_playlist error` appare con alcune dirette.**
Alcune playlist con sessione protetta non sono leggibili da ffmpeg. I video registrati funzionano normalmente.

## Avvertenza

Usa il programma solo per contenuti a cui hai diritto di accedere e nel rispetto dei termini di servizio di FloGrappling. Il progetto non è affiliato a FloGrappling.

