"""
Script de test pour vérifier l'installation et le bon fonctionnement du système.
"""

import sys
import logging
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def test_imports():
    """Teste que toutes les dépendances sont installées."""
    print("\n" + "="*60)
    print("TEST 1: Vérification des imports")
    print("="*60)
    
    required_modules = {
        'ollama': 'ollama',
        'pymupdf (fitz)': 'fitz',
        'python-docx': 'docx',
        'Pillow': 'PIL',
    }
    
    all_ok = True
    
    for name, module in required_modules.items():
        try:
            __import__(module)
            print(f"✅ {name} : OK")
        except ImportError:
            print(f"❌ {name} : MANQUANT")
            print(f"   → Installer avec: pip install {name.split()[0]}")
            all_ok = False
    
    return all_ok

def test_ollama_connection():
    """Teste la connexion à Ollama."""
    print("\n" + "="*60)
    print("TEST 2: Connexion à Ollama")
    print("="*60)
    
    try:
        import ollama
        models = ollama.list()
        print(f"✅ Ollama est accessible")
        print(f"   Modèles installés: {len(models.get('models', []))}")
        return True
    except Exception as e:
        print(f"❌ Impossible de se connecter à Ollama")
        print(f"   Erreur: {e}")
        print(f"   → Vérifiez qu'Ollama est installé et en cours d'exécution")
        print(f"   → Lancez 'ollama serve' dans un terminal")
        return False

def test_models_availability():
    """Vérifie que les modèles requis sont disponibles."""
    print("\n" + "="*60)
    print("TEST 3: Modèles disponibles")
    print("="*60)
    
    try:
        import ollama
        from config import TEXT_MODEL, VISION_MODEL
        
        models = ollama.list()
        available_models = [m['name'] for m in models.get('models', [])]
        
        # Vérifier le modèle de texte
        text_ok = TEXT_MODEL in available_models
        if text_ok:
            print(f"✅ Modèle de texte: {TEXT_MODEL}")
        else:
            print(f"❌ Modèle de texte manquant: {TEXT_MODEL}")
            print(f"   → Télécharger avec: ollama pull {TEXT_MODEL}")
        
        # Vérifier le modèle de vision
        vision_ok = VISION_MODEL in available_models
        if vision_ok:
            print(f"✅ Modèle de vision: {VISION_MODEL}")
        else:
            print(f"⚠️  Modèle de vision manquant: {VISION_MODEL}")
            print(f"   → Télécharger avec: ollama pull {VISION_MODEL}")
            print(f"   → L'analyse d'images ne sera pas disponible")
        
        print(f"\nModèles disponibles:")
        for model in available_models:
            print(f"   - {model}")
        
        return text_ok
        
    except Exception as e:
        print(f"❌ Erreur lors de la vérification des modèles: {e}")
        return False

def test_modules_import():
    """Teste l'import des modules du projet."""
    print("\n" + "="*60)
    print("TEST 4: Import des modules du projet")
    print("="*60)
    
    modules = [
        'config',
        'document_extractor',
        'image_analyzer',
        'markdown_processor',
        'notes_generator'
    ]
    
    all_ok = True
    
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}.py : OK")
        except Exception as e:
            print(f"❌ {module}.py : ERREUR")
            print(f"   {str(e)}")
            all_ok = False
    
    return all_ok

def test_directories():
    """Vérifie la structure des dossiers."""
    print("\n" + "="*60)
    print("TEST 5: Structure des dossiers")
    print("="*60)
    
    from config import INPUT_FOLDER, OUTPUT_FOLDER
    
    input_path = Path(INPUT_FOLDER)
    output_path = Path(OUTPUT_FOLDER)
    
    # Vérifier le dossier d'entrée
    if input_path.exists():
        files = list(input_path.glob("**/*.pdf")) + list(input_path.glob("**/*.docx"))
        print(f"✅ Dossier d'entrée: {INPUT_FOLDER}")
        print(f"   Documents trouvés: {len(files)}")
        if files:
            print(f"   Exemples:")
            for f in files[:3]:
                print(f"     - {f.name}")
    else:
        print(f"⚠️  Dossier d'entrée manquant: {INPUT_FOLDER}")
        print(f"   → Le dossier sera créé automatiquement")
        input_path.mkdir(parents=True, exist_ok=True)
    
    # Vérifier le dossier de sortie
    if output_path.exists():
        print(f"✅ Dossier de sortie: {OUTPUT_FOLDER}")
    else:
        print(f"⚠️  Dossier de sortie manquant: {OUTPUT_FOLDER}")
        print(f"   → Le dossier sera créé automatiquement")
        output_path.mkdir(parents=True, exist_ok=True)
    
    return True

def test_simple_processing():
    """Test simple de traitement (si des documents sont disponibles)."""
    print("\n" + "="*60)
    print("TEST 6: Test de traitement (optionnel)")
    print("="*60)
    
    from config import INPUT_FOLDER
    input_path = Path(INPUT_FOLDER)
    
    test_files = list(input_path.glob("**/*.pdf"))[:1] + list(input_path.glob("**/*.docx"))[:1]
    
    if not test_files:
        print("⚠️  Aucun document de test disponible")
        print(f"   → Placez un PDF ou DOCX dans '{INPUT_FOLDER}' pour tester")
        print(f"   → Vous pouvez exécuter manuellement:")
        print(f"      python main.py doc_to_markdown 1 --no-images")
        return True
    
    print(f"📄 Fichier de test trouvé: {test_files[0].name}")
    print(f"   Pour tester le traitement, exécutez:")
    print(f"   python main.py doc_to_markdown 1 --no-images")
    
    return True

def run_all_tests():
    """Exécute tous les tests."""
    print("\n" + "#"*60)
    print("# TESTS DE VÉRIFICATION DU SYSTÈME")
    print("#"*60)
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports Python", test_imports()))
    
    # Test 2: Ollama
    results.append(("Connexion Ollama", test_ollama_connection()))
    
    # Test 3: Modèles
    results.append(("Modèles requis", test_models_availability()))
    
    # Test 4: Modules projet
    results.append(("Modules du projet", test_modules_import()))
    
    # Test 5: Dossiers
    results.append(("Structure dossiers", test_directories()))
    
    # Test 6: Traitement
    results.append(("Test de traitement", test_simple_processing()))
    
    # Résumé
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS")
    print("="*60)
    
    success_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for test_name, result in results:
        status = "✅ PASSÉ" if result else "❌ ÉCHOUÉ"
        print(f"{status} - {test_name}")
    
    print("\n" + "="*60)
    
    if success_count == total_count:
        print("🎉 TOUS LES TESTS SONT PASSÉS!")
        print("   Le système est prêt à être utilisé.")
        print("\nPour commencer:")
        print("   1. Placez vos documents dans 'docs-bruts/'")
        print("   2. Exécutez: python main.py doc_to_markdown 4")
        return True
    else:
        print(f"⚠️  {total_count - success_count} test(s) échoué(s)")
        print("   Consultez les messages ci-dessus pour corriger les problèmes.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
