"""
torch-nn: modulo di utilità per la gestione del train, test e validazione di una rete torch
"""

# Importiamo tutte le librerire necessarie
import torch
from torch import nn
from torch.utils.data import DataLoader
from sklearn.metrics import precision_score, recall_score, f1_score
import matplotlib.pyplot as plt
from tqdm import trange
from inspect import signature

"""
    dizionario con i valori di default della configurazione
"""
config = {
    "learning_rate": 1e-3,
    "batch_size": 64,
    "epochs": 20,
    "patience": 5,
    "min_delta": 0.01,
    "momentum": 0.9,
    "nesterov": True,
    "train_loss": nn.CrossEntropyLoss(),
    "test_loss": nn.NLLLoss(),
    "metrics": [precision_score, recall_score, f1_score],
    "metric_average": 'macro'
}


def make_dataloaders(train_data, val_data, test_data, 
                     batch=config["batch_size"], prefetch=12, no_pagemem=True):

    """costruisce i dataloaders di train, validazione e test a partire dai rispettivi dataset.

    Args:
        train_data (torch.utils.data.Dataset): data set di training
        val_data (torch.utils.data.Dataset): data set di validazione
        test_data (torch.utils.data.Dataset): data set di test
        batch (int, optional): dimenssione del batch. Defaults to config["batch_size"].
        prefetch (int, optional): n. di batch precaricati in ogni sottoprocesso. Defaults to 12.
        pagemem (bool, optional): uso della memoria non paginata per i tensori. Defaults to True.
    
    Returns:
        dataloaders (tuple[torch.utils.data.Dataloader, torch.utils.data.Dataloader, torch.utils.data.Dataloader]): una tupla contenente i tre dataloader
    """
    # Creiamo i data loaders che saranno gli iteraboili che generano i batch di
    # addestramento e/o test
    train_dataloader = DataLoader(train_data,
                                batch_size=batch,           # Imposta la dimensione del batch
                                shuffle=True,               # Shuffling dei batch tra un'epoca e l'altra
                                num_workers=2,              # Numero dei sottoprocessi di caricamento dei dati
                                prefetch_factor=prefetch,   # Batch precaricati da ogni sottoprocesso
                                pin_memory=no_pagemem)      # Usa la memoria non paginata per muovere i tensori
                                                            # da CPU a GPU
    val_dataloader = DataLoader(val_data,
                                batch_size=batch,
                                shuffle=True,
                                num_workers=2,
                                prefetch_factor=prefetch,
                                pin_memory=no_pagemem)

    test_dataloader = DataLoader(test_data,
                                batch_size=batch,
                                shuffle=True,
                                num_workers=2,
                                prefetch_factor=prefetch,
                                pin_memory=no_pagemem)

    # semplice investigazione della shape dei tensori: usiamo il primo
    # batch del test dataloader come esempio
    for X, y in test_dataloader:
        print(f"Shape e tipo dei campioni: {X.shape}, {X.dtype}")
        print(f"Shape e tipo delle etichette: {y.shape} {y.dtype}")
        break
    
    dataloaders = (train_dataloader, val_dataloader, test_dataloader)
    return dataloaders


class EarlyStopping:
    """Implementazione del Early Stopping
    
        Args:
            patience (int): numero epoche di pazienza
            min_delta (float): incremento minimo della loss di validazione 
    """
    def __init__(self, 
                 patience=config["patience"], 
                 min_delta=config["min_delta"]):

        self.patience = patience
        self.min_delta = min_delta              # valore minimo di decrescita della loss di validazione all'epoca corrente
                                                # per asserire che c'è un miglioramenti della loss
        self.counter = 0                        # contatore delle epoche di pazienza
        self.early_stop = False                 # flag di early stop
        self.min_validation_loss = torch.inf    # valore corrente ottimo della loss di validazione

    def __call__(self, validation_loss):
        """chiamata in forma funzionale dell'oggetto di classe EarlySopping

        Args:
            validation_loss (float): valore della loss di validazione
        """

        # chiamata in forma funzionale dell'oggetto di classe EarlySopping

        if (validation_loss + self.min_delta) >= self.min_validation_loss:  # la loss di validazione non decresce
            self.counter += 1                                               # incrementiamo il contatore delle epoche di pazienza
            if self.counter >= self.patience:
                self.early_stop = True
        else:                                                   # c'è un miglioramento della loss:
            self.min_validation_loss = validation_loss          # consideriamo la loss corrente
                                                                # come nuova loss ottimale
            self.counter = 0                                    # e azzeriamo il contatore di pazienza


def train_loop(model, 
               dataloader, 
               optimizer, 
               device, 
               pbar, 
               loss_fn=config["train_loss"]):
    """Ciclo di addestramento sui batch di un'epoca

    Args:
        model (torch.nn.Module): classe del modello neurale
        dataloader (torch.utils.data.Dataloader): dataloader di addestramento
        optimizer (torch.optim.Optimizer): ottimizzatore
        device (torch.device or int or str): device di esecuzione dell'addestramento
        pbar (tqdm): progress bar
        loss_fn (optional): loss di addestramento definita in ``torch.nn``. Defaults to config["train_loss"]

    Returns:
        float: loss media sui batch
    """

    num_batches = len(dataloader)
    epoch_loss = 0.0

    # Impostiamo la modalità di training del modello: è una best practice che serve per il
    # dropout e/o batch normalization
    model.train()
    for _, (X, y) in zip(pbar,dataloader):      # questa iterazione fatta così garantisce l'avanzamento della progress
                                                # bar mentre i batch vengono prelevati dal dataloader

        # Spostiamo esplicitamente i tensori sul device di computazione
        X, y = X.to(device), y.to(device)

        # Passo esplicito di addestramento
        optimizer.zero_grad()                   # azzeriamo i gradienti dell'iterata precedente

        # Calcoliamo la loss ed effettuiamo la predizione del minibatch
        logits = model(X)
        batch_loss = loss_fn(logits, y)

        epoch_loss += batch_loss.item()

        batch_loss.backward()             # step di backpropagation

        optimizer.step()                  # passo di ottimizzazione e aggiornamento dei parametri


    # Ritorniamo la loss media dell'epoca
    return epoch_loss/num_batches

def eval_loop(model, 
              dataloader, 
              device, 
              loss_fn=config["test_loss"], 
              metrics=config["metrics"],
              average=config["metric_average"]):
    """ciclo di test/validazione su un'epoca

    Args:
        model (torch.nn.Module): classe del modello neurale
        dataloader (torch.utils.data.Dataloader): dataloader di test/validazione
        device (torch.device or int or str): device di esecuzione dell'addestramento
        loss_fn (optional): loss di test/validazione definita in ``torch.nn``. Defaults to config["test_loss"]
        metrics (list[callable(y_true, y_pred, **kwargs)], optional): lista delle metriche definite dall'utente che possono o meno avere un parametro average per la gestione delle metriche multiclasse. Defaults to config["metrics"]
        average (string|None, optional): parametro di calcolo delle metriche medie multiclasse. Segue la convenzione di sklearn: {‘micro’, ‘macro’, ‘samples’, ‘weighted’, ‘binary’} or None. Defaluts to config["metric_average"]

    Returns:
        tuple[float, float, dict[]]: loss di test/validazione, accuracy, dizionario dei valori delle metriche definite nella configurazione e calcolate sull'epoca
    """

    # Impostiamo la modalità di valutazione del modello: è una best practice che serve per il
    # dropout e/o batch normalization
    model.eval()

    size = len(dataloader.dataset)
    num_batches = len(dataloader)
    test_loss, accuracy = 0.0, 0

    y_true = []
    y_pred = []

    # context manager che disabilita esplicitamente il calcolo dei gradienti in fase di test
    with torch.no_grad():
        for X, y in dataloader:

            # Spostiamo esplicitamente i tensori sul device di computazione
            X, y = X.to(device), y.to(device)

            pred = model(X)
            test_loss += loss_fn(pred, y).item()

            # L'accuracy sul batch si calcola creando il tensore di dimensione pari al batch
            # per cui i massimi argomenti di ogni predizione sono uguali alla classe predetta
            # per il singolo campione, poi convertendo questo tensore di booleani in un vettore
            # binario di tipo float, sommando i valori 1 ed estraendo lo scalare contenuto nel tensore risultato
            accuracy += (pred.argmax(1) == y).type(torch.float).sum().item()

            y_true.extend(y.cpu().numpy())
            y_pred.extend(pred.argmax(1).cpu().numpy())

    test_loss /= num_batches
    accuracy /= size            # Per quanto detto prima, l'accuracy media va calcolata sulla dimensione del data set

    # Calcoliamo il dizionario delle metriche per epoca
    epoch_metrics = {}
    for metric in metrics:
        epoch_metrics[metric.__name__] = metric(y_true, y_pred, average=average) \
                if 'average' in signature(metric).parameters.keys() \
                else metric(y_true, y_pred)

    return test_loss, accuracy, epoch_metrics

 
def train_test(model,
               optimizer,
               device,
               train_dataloader,
               test_dataloader,
               epochs=config["epochs"],
               train_loss_fn=config["train_loss"],
               test_loss_fn=config["test_loss"],
               early_stopping=None,     # posso addestrare senza early stopping
               val_dataloader=None,     # e in questo caso non c'è validation set
               scheduler=None,          # possibile scheduler per monitorare l'andamento di un iperparametro, tipicamente il learning rate
               metrics=config["metrics"],
               average=config["metric_average"]):
    """Ciclo di addestramento completo con test, early stopping e scheduler del learning rate

    Args:
        model (torch.nn.Module): classe del modello neurale
        optimizer (torch.optim.Optimizer): ottimizzatore
        device (torch.device or int or str): device di esecuzione dell'addestramento/test
        train_dataloader (torch.utils.data.Dataloader): dataloader di addestramento
        test_dataloader (torch.utils.data.Dataloader): dataloader di test
        epochs (int): numero di epoche. Defaults to config["epochs"]
        train_loss_fn (optional): loss di addestramento definita in ``torch.nn``. Defaults to config["train_loss"]
        test_loss_fn (optional): loss di test/validazione definita in ``torch.nn``. Defaults to config["test_loss"]
        early_stopping (EarlyStopping, optional): classe di early stopping se presente. Defaults to None.
        metrics (list[callable(y_true, y_pred, **kwargs)], optional): lista delle metriche definite dall'utente che possono o meno avere un parametro average per la gestione delle metriche multiclasse. Defaults to config["metrics"]
        average (string|None, optional): parametro di calcolo delle metriche medie multiclasse. Segue la convenzione di sklearn: {‘micro’, ‘macro’, ‘samples’, ‘weighted’, ‘binary’} or None. Defaluts to config["metric_average"]

    Returns:
        tuple[float, float, float, list[float], dict[list[float]]]: valori delle loss di train, test e validazione, lista dei valori di accuracy per epoca, dizionario con le liste dei valori delle metriche per epoca
    """
                                    

    # liste dei valori di loss e accuracy epoca per epoca per il plot
    train_loss, validation_loss, test_loss = [], [], []
    accuracy = []
    
    # dizionario delle liste dei valori delle metriche di test epoca per epoca
    test_metrics = {}   
    for metric in metrics:
        test_metrics[metric.__name__] = []

    num_batches = len(train_dataloader.batch_sampler) # il campionatore dei batch del dataloader ha il protocollo 
                                                      # __len__ e può fornirci il numero dei batch campionabili

    # Ciclo di addestramento con early stopping
    for epoch in range(1,epochs+1):

        # Progress bar
        pbar = trange(num_batches)
        pbar.set_description(desc='Epoch {:4d}'.format(epoch))

        epoch_train_loss = train_loop(model, train_dataloader, optimizer, device, pbar, loss_fn=train_loss_fn)
        train_loss.append(epoch_train_loss)

        # validation se è presente val_dataloader
        if val_dataloader != None:
                epoch_validate_loss, _, _ = eval_loop(model, val_dataloader, device, loss_fn=test_loss_fn, metrics=metrics, average=average)
                validation_loss.append(epoch_validate_loss)

        # test 
        epoch_test_loss, epoch_accuracy, epoch_metrics = eval_loop(model, test_dataloader, device, loss_fn=test_loss_fn, metrics=metrics, average=average)

        test_loss.append(epoch_test_loss)
        accuracy.append(epoch_accuracy)
        for metric in metrics:
            test_metrics[metric.__name__].append(epoch_metrics[metric.__name__])


        val_str = f'Validation loss: {epoch_validate_loss:6.4f}\n' if val_dataloader != None else ' '

        print(f"Train loss: {epoch_train_loss:6.4f}\n{val_str}Test loss: {epoch_test_loss:6.4f} Accuracy: {epoch_accuracy:6.2f}\nMetrics:")
        
        for label, metric in epoch_metrics.items():     
              print(f'{label}: {metric:6.2f} ', end=' ')
        
        print()

        # early stopping
        if early_stopping != None:
            early_stopping(epoch_validate_loss)
            if early_stopping.early_stop:
                break

        # scheduler dell'iperparametro
        if scheduler != None:
            scheduler.step()

    return train_loss, validation_loss, test_loss, accuracy, test_metrics

def save_model(net, optimizer, current_epoch, train_loss, val_loss, test_loss, accuracy, metrics, path):
    """Salvataggio del modello con tutte le informazioni di stato e le metriche in un file pickle

    Args:
        net (torch.nn.Module): classe del modello neurale
        optimizer (torch.optim.Optimizer): ottimizzatore
        current_epoch (int): numero di epoche di addestramento
        train_loss (list[float]): lista dei valori della loss di addestramento
        val_loss (list[float]): lista dei valori della loss di validazione
        test_loss (list[float]): lista dei valori della loss di test
        accuracy (list[float]): lista dei valori dell'accuracy
        metrics (dict[list[float]]): liste dei valori delle metriche definite dall'utente
        path (os.path): percorso completo del file di salvataggio
    """

    # Abbiamo deciso per queste informazioni, ma possiamo caricare qualunque cosa
    to_save = {
            'epoch': current_epoch,
            'model_state_dict': net.state_dict(),               # configurazione di tutti i layer *addestrabili* del modello
            'optimizer_state_dict': optimizer.state_dict(),     # configurazione e operparametri dell'ottimizzatore
            'training_loss': train_loss,
            'validation_loss': val_loss,
            'test_loss': test_loss,
            'accuracy': accuracy
    }
    
    to_save.update(metrics)
    
    torch.save(to_save, path)


def load_model(path, model, optimizer, device = None):
    """  Ricarichiamo il dizionario e restituiamo la tupla delle informazioni. La rete e l'ottimizzatore devono essere inizializzati prima chiamare la funzione

    Args:
        path (os.path): percorso completo del file del modello
        model (torch.nn.Module): modello inizializzato
        optimizer (torch.optim.Optimizer): ottimizzatore inizializzato
        device (torch.device or int or str): device di caricamento del modello. Defaults to None.

    Returns:
        tuple[torch.nn.Module, torch.optim.Optimizer, Any]: tupla contenente il modello, l'ottimizzatore e tutto lo stato conservato da ``save_model()``
    """


    # Se il device è specificato e non è la CPU, allora muoviamo il modello sul device
    if device != None and device != 'cpu':
        model.to(device)

    # carichiamo il model checkpoint
    checkpoint = torch.load(path)

    # inizializziamo lo stato del modello e dell'ottimizzatore
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

    # restituiamo tutte le informazioni in una tupla
    return (model,
            optimizer,
            checkpoint
            )

def displayLosses(train_loss, test_loss, validation_loss):
    """plot dell'andamento delle loss di addestramento/validazione/test lungo le epoche di addestramento

    Args:
        train_loss (list[float]): loss di addestramento
        test_loss (list[float]): loss di test
        validation_loss (list[float]): loss di validazione
    """
        
    epochs = range(1, len(train_loss)+1) # calcolo del range delle epoche
    
    plt.plot(epochs, train_loss, label='training loss')
    plt.plot(epochs,validation_loss, label='validation loss')
    plt.plot(epochs, test_loss, label='test loss')
    plt.legend(loc='lower right')
    plt.title("Loss di addestramento")
    plt.ylim(0,1)
    plt.show()
    

def displayMetrics(accuracy, metrics):
    """plot dell'andamento dell'accuracy di addestramento e delle metriche di test lungo le epoche di addestramento

    Args:
        accuracy (list[float]): accuracy di addestramento
        metrics (tuple[list[float]]): dizionario delle metriche di test
    """
    epochs = range(1, len(accuracy)+1) # calcolo del range delle epoche
    
    plt.plot(epochs, accuracy, label="train acc.")
    
    for label, metric in metrics.items():
        plt.plot(epochs, metric, label=label)
    
    plt.legend(loc='lower right')
    plt.title("Metriche")
    plt.ylim(0,1)
    plt.show()
    
    