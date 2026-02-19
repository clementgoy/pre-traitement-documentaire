"""
Orchestrateur principal pour le pré-traitement de documents.
Supporte deux pipelines:
1. raw_to_notes: Conversion de notes brutes en markdown (ancien système)
2. doc_to_markdown: Conversion de documents (PDF/DOCX) en markdown enrichi (nouveau système)
"""

from concurrent.futures import ThreadPoolExecutor
import glob
import os
import logging
import sys
from pathlib import Path

from notes_generator import NotesGenerator
from markdown_processor import MarkdownProcessor
from config import TEXT_MODEL, VISION_MODEL, MAX_THREADS, INPUT_FOLDER, OUTPUT_FOLDER

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# ============================================================================
# ANCIEN PIPELINE: raw_to_notes (notes brutes vers markdown)
# ============================================================================

def process_raw_to_notes(file_path, notes_generator):
    try:
        notes_generator.process_transcript(file_path)
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")

def run_raw_to_notes(model, max_threads, folder):
    notes_generator = NotesGenerator(model=model, max_tokens=4096)

    # Get all transcript files from input directory
    raw_files = glob.glob(os.path.join(folder, "**/*.raw.txt"), recursive=True)
    # Initialize a list to store raw files without corresponding notes files
    filtered_raw_files = []

    # Iterate over the raw files
    for raw_file in raw_files:
        # Get the name of the raw file without the extension
        raw_file_name = os.path.splitext(os.path.basename(raw_file))[0]
        # Check if a corresponding notes file exists
        model_name = model.replace(":", "_")
        notes_file = os.path.join(
            os.path.dirname(raw_file), raw_file_name + f".{model_name}" + ".notes.md"
        )
        if not os.path.exists(notes_file):
            # If notes file does not exist, add the raw file to the filtered list
            filtered_raw_files.append(raw_file)
    
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [
            executor.submit(process_raw_to_notes, file, notes_generator)
            for file in filtered_raw_files
        ]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error in transcript to notes thread: {e}")

# ============================================================================
# NOUVEAU PIPELINE: doc_to_markdown (documents vers markdown enrichi)
# ============================================================================

def process_single_document(file_path, processor, output_folder):
    """Traite un document unique."""
    try:
        output_path = Path(output_folder) / f"{Path(file_path).stem}.md"
        processor.process_document(file_path, str(output_path))
    except Exception as e:
        logging.error(f"Error processing document {file_path}: {e}")

def run_doc_to_markdown(text_model, vision_model, max_threads, input_folder, output_folder, analyze_images=True, enrich_text=False):
    """
    Traite des documents (PDF/DOCX) et les convertit en Markdown enrichi.
    
    Args:
        text_model: Modèle pour le traitement de texte
        vision_model: Modèle multimodal pour l'analyse d'images
        max_threads: Nombre de threads pour le traitement parallèle
        input_folder: Dossier des documents sources
        output_folder: Dossier de sortie
        analyze_images: Activer l'analyse d'images (True/False)
        enrich_text: Activer l'enrichissement du texte via LLM (True/False)
    """
    if enrich_text:
        logging.info("Pipeline doc_to_markdown - Mode: ENRICHI (extraction algo + LLM images + LLM texte)")
        logging.warning("AVERTISSEMENT: Risque <5% d'ajout d'information par le LLM textuel")
    else:
        logging.info("Pipeline doc_to_markdown - Mode: FIDÈLE (extraction algorithme pure + LLM images)")
        logging.info("GARANTIE: 100% fidèle sur texte/tableaux, LLM uniquement pour transcription images")
    
    logging.info(f"Analyse d'images: {analyze_images}")
    logging.info(f"Modèle texte: {text_model}, Modèle vision: {vision_model}")
    
    processor = MarkdownProcessor(
        text_model=text_model,
        vision_model=vision_model,
        analyze_images=analyze_images,
        enrich_text=enrich_text
    )
    
    # Trouver tous les documents supportés
    input_path = Path(input_folder)
    supported_files = []
    
    for ext in ['pdf', 'docx', 'doc']:
        files = list(input_path.glob(f"**/*.{ext}"))
        supported_files.extend(files)
    
    if not supported_files:
        logging.warning(f"Aucun document trouvé dans {input_folder}")
        return
    
    logging.info(f"Trouvé {len(supported_files)} document(s) à traiter")
    
    # Filtrer les fichiers déjà traités
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    
    filtered_files = []
    for doc_file in supported_files:
        model_name = text_model.replace(":", "_")
        output_file = output_path / f"{doc_file.stem}.{model_name}.md"
        
        if not output_file.exists():
            filtered_files.append(doc_file)
        else:
            logging.info(f"Fichier déjà traité: {doc_file.name}")
    
    if not filtered_files:
        logging.info("Tous les documents ont déjà été traités")
        return
    
    logging.info(f"Traitement de {len(filtered_files)} nouveau(x) document(s)")
    
    # Traitement parallèle ou séquentiel selon max_threads
    if max_threads > 1:
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [
                executor.submit(process_single_document, str(file), processor, output_folder)
                for file in filtered_files
            ]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error in document processing thread: {e}")
    else:
        # Traitement séquentiel
        for file in filtered_files:
            process_single_document(str(file), processor, output_folder)

# ============================================================================
# MAIN
# ============================================================================

def main(pipeline, model, max_threads, folder, **kwargs):
    if pipeline == "raw_to_notes":
        run_raw_to_notes(model, max_threads, folder)
    elif pipeline == "doc_to_markdown":
        vision_model = kwargs.get('vision_model', VISION_MODEL)
        output_folder = kwargs.get('output_folder', OUTPUT_FOLDER)
        analyze_images = kwargs.get('analyze_images', True)
        enrich_text = kwargs.get('enrich_text', False)
        
        run_doc_to_markdown(
            text_model=model,
            vision_model=vision_model,
            max_threads=max_threads,
            input_folder=folder,
            output_folder=output_folder,
            analyze_images=analyze_images,
            enrich_text=enrich_text
        )
    else:
        logging.error(f"Unknown pipeline: {pipeline}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Pipeline 1 (notes brutes):")
        print("    python main.py raw_to_notes <max_threads> <model> <folder>")
        print()
        print("  Pipeline 2 (documents enrichis):")
        print("    python main.py doc_to_markdown <max_threads> [options]")
        print()
        print("Options pour doc_to_markdown:")
        print("  --text-model <model>      Modèle de texte (défaut: ministral3:14b)")
        print("  --vision-model <model>    Modèle de vision (défaut: llava:13b)")
        print("  --input <folder>          Dossier d'entrée (défaut: docs-bruts)")
        print("  --output <folder>         Dossier de sortie (défaut: docs-traites)")
        print("  --no-images               Désactiver l'analyse d'images")
        print("  --enrich                  Mode ENRICHI : ajoute nettoyage LLM du texte (améliore structure)")
        print("")
        print("Mode par défaut : FIDÈLE (extraction algorithme pure + LLM pour images)")
        print("                   Garantie 100% sur texte/tableaux, LLM uniquement pour images")
        print("Mode --enrich   : Ajoute nettoyage LLM du texte (risque <5% d'ajout, meilleure structure)")
        print()
        print("Exemples:")
        print("  python main.py doc_to_markdown 4              # Mode FIDÈLE par défaut (algo + images)")
        print("  python main.py doc_to_markdown 4 --enrich     # Mode ENRICHI (+ LLM texte)")
        print("  python main.py doc_to_markdown 2 --vision-model llava:34b")
        print("  python main.py doc_to_markdown 4 --no-images  # Sans analyse d'images")
        sys.exit(1)

    pipeline = sys.argv[1]
    
    if pipeline == "raw_to_notes":
        # Ancien format
        if len(sys.argv) != 5:
            print("Usage: python main.py raw_to_notes <max_threads> <model> <folder>")
            sys.exit(1)
        
        max_threads = int(sys.argv[2])
        model = sys.argv[3]
        folder = sys.argv[4]
        
        logging.info("Starting note generation process (raw_to_notes)")
        main(pipeline, model, max_threads, folder)
        logging.info("Completed note generation process")
    
    elif pipeline == "doc_to_markdown":
        # Nouveau format avec options
        max_threads = int(sys.argv[2]) if len(sys.argv) > 2 else MAX_THREADS
        
        # Parser les options
        text_model = TEXT_MODEL
        vision_model = VISION_MODEL
        input_folder = INPUT_FOLDER
        output_folder = OUTPUT_FOLDER
        analyze_images = True
        enrich_text = False
        
        i = 3
        while i < len(sys.argv):
            arg = sys.argv[i]
            
            if arg == "--text-model" and i + 1 < len(sys.argv):
                text_model = sys.argv[i + 1]
                i += 2
            elif arg == "--vision-model" and i + 1 < len(sys.argv):
                vision_model = sys.argv[i + 1]
                i += 2
            elif arg == "--input" and i + 1 < len(sys.argv):
                input_folder = sys.argv[i + 1]
                i += 2
            elif arg == "--output" and i + 1 < len(sys.argv):
                output_folder = sys.argv[i + 1]
                i += 2
            elif arg == "--no-images":
                analyze_images = False
                i += 1
            elif arg == "--enrich":
                enrich_text = True
                i += 1
            else:
                logging.warning(f"Option inconnue: {arg}")
                i += 1
        
        logging.info("Starting document processing (doc_to_markdown)")
        main(
            pipeline, 
            text_model, 
            max_threads, 
            input_folder,
            vision_model=vision_model,
            output_folder=output_folder,
            analyze_images=analyze_images,
            enrich_text=enrich_text
        )
        logging.info("Completed document processing")
    
    else:
        logging.error(f"Unknown pipeline: {pipeline}")
        sys.exit(1)