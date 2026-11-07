import io, json, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import prepare_fotos as pf
import build_graph as bg
from PIL import Image


def jpg(cor=(200, 40, 40), size=(300, 400)):
    b = io.BytesIO()
    Image.new("RGB", size, cor).save(b, "JPEG")
    return b.getvalue()


class Fotos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.repo, self.orig, self.out = (os.path.join(t, d) for d in ("repo", "orig", "saida"))
        for p, nome in (("SP/ana-lima", "Ana Lima"), ("RJ/flavio-bolsonaro", "Flávio Bolsonaro"),
                        ("BA/joao-silva", "João Silva"), ("MG/sem-foto", "Pessoa Sem Foto"),
                        ("PR/sem-candidatura", "Fulano Sem Candidatura")):
            os.makedirs(os.path.dirname(os.path.join(self.repo, p)), exist_ok=True)
            with open(os.path.join(self.repo, p + ".md"), "w", encoding="utf-8") as f:
                f.write(f"# {nome}\n\n## Histórico\n\n")
        os.makedirs(os.path.join(self.repo, "_meta"))
        tse = [
            {"slug": "ana-lima", "name": "Ana Lima", "role": "Candidato(a) a Deputado Estadual (SP) — Eleição 2026", "aliases": ["Ana Lima"], "tse_sequencial": "250000000001"},
            # mandato + candidatura: slug diferente do arquivo, casa por nome+UF
            {"slug": "flavio-bolsonaro-br", "name": "Flávio Bolsonaro", "role": "Candidato(a) a Presidente (RJ) — Eleição 2026", "aliases": ["Flávio Bolsonaro"], "tse_sequencial": "190000000002"},
            # nome ambíguo: dois João Silva em UFs diferentes, arquivo está na pasta BA
            {"slug": "joao-silva-sp", "name": "João Silva", "role": "Candidato(a) a Deputado Estadual (SP) — Eleição 2026", "aliases": ["João Silva"], "tse_sequencial": "250000000003"},
            {"slug": "joao-silva-mg", "name": "João Silva", "role": "Candidato(a) a Deputado Estadual (MG) — Eleição 2026", "aliases": ["João Silva"], "tse_sequencial": "130000000004"},
            {"slug": "sem-foto", "name": "Pessoa Sem Foto", "role": "Candidato(a) a Senador (MG) — Eleição 2026", "aliases": ["Pessoa Sem Foto"], "tse_sequencial": "130000000005"},
        ]
        with open(os.path.join(self.repo, "_meta", "politicians_tse.json"), "w", encoding="utf-8") as f:
            json.dump(tse, f)
        os.makedirs(os.path.join(self.orig, "extra"))
        with zipfile.ZipFile(os.path.join(self.orig, "foto_cand2026_SP_div.zip"), "w") as z:
            z.writestr("FSP250000000001_div.jpg", jpg())
            z.writestr("FSP250000000003_div.jpg", jpg())
        with open(os.path.join(self.orig, "extra", "FRJ190000000002_div.jpg"), "wb") as f:
            f.write(jpg((20, 90, 200)))  # arquivo solto, fora de ZIP
        self.graph = {"nodes": [[s, s, "politico", None, 1] for s in
                                ("ana-lima", "flavio-bolsonaro", "joao-silva", "sem-foto", "sem-candidatura")]
                      + [["e-tcu", "TCU", "orgao", None, 3]]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_extrai_sq_do_nome(self):
        self.assertEqual(pf.seq_do_arquivo("FSP250001234567_div.jpg"), "250001234567")
        self.assertIsNone(pf.seq_do_arquivo("semnumero.jpg"))

    def test_gera_miniaturas_e_relata(self):
        r = pf.preparar(self.graph, self.repo, self.orig, self.out)
        self.assertEqual(r["ok"], 2)
        for slug in ("ana-lima", "flavio-bolsonaro"):
            with Image.open(os.path.join(self.out, f"{slug}.jpg")) as im:
                self.assertEqual(im.size, (pf.TAMANHO, pf.TAMANHO))
                self.assertEqual(im.format, "JPEG")
        self.assertEqual(r["metodos"], {"slug": 1, "nome+uf": 1})
        self.assertEqual(r["ambiguos"], ["João Silva"])
        self.assertEqual(r["sem_foto"], ["Pessoa Sem Foto"])
        self.assertEqual(r["sem_candidatura"], ["Fulano Sem Candidatura"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "e-tcu.jpg")))  # só políticos

    def test_build_graph_usa_as_miniaturas(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, "helena-arantes.jpg"), "wb") as f:
            f.write(jpg())
        amostra = os.path.join(os.path.dirname(__file__), "..", "amostra")
        cur = bg.load_curadas(os.path.join(os.path.dirname(__file__), "..", "entidades_curadas.json"))
        g = bg.build(amostra, cur, 2, 1, 10, 100, self.out)
        fotos = {n[0]: n[3] for n in g["nodes"] if n[2] == "politico"}
        self.assertEqual(fotos["helena-arantes"], "fotos/helena-arantes.jpg")
        self.assertIsNone(fotos["otavio-brandao"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
