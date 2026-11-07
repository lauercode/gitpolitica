import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build_graph as bg

AMOSTRA = os.path.join(os.path.dirname(__file__), "..", "amostra")
CUR = bg.load_curadas(os.path.join(os.path.dirname(__file__), "..", "entidades_curadas.json"))


def graph(**kw):
    args = dict(min_news=2, min_link=1, max_part=10, top=100, fotos=None)
    args.update(kw)
    g = bg.build(AMOSTRA, CUR, **args)
    nomes = {n[0]: n for n in g["nodes"]}
    ligs = {frozenset(l[:2]): l[2] for l in g["links"]}
    return g, nomes, ligs


class Extracao(unittest.TestCase):
    def test_tipos(self):
        e = bg.extract("CPI do Asfalto convoca Rui Camargo e diretores do Banco Meridiano; PF e TSE acompanham", CUR, set())
        self.assertIn(("CPI do Asfalto", "escandalo"), e)
        self.assertIn(("Rui Camargo", "pessoa"), e)
        self.assertIn(("Banco Meridiano", "empresa"), e)
        self.assertIn(("Polícia Federal", "orgao"), e)
        self.assertIn(("TSE", "orgao"), e)

    def test_titulo_removido_e_politico_ignorado(self):
        e = bg.extract("Deputada Helena Arantes defende contrato", CUR, {"helena-arantes"})
        self.assertFalse([x for x in e if x[1] == "pessoa"])


class Grafo(unittest.TestCase):
    def test_ligacao_politico_politico_por_noticia_comum(self):
        _, _, ligs = graph()
        self.assertEqual(len(ligs[frozenset({"helena-arantes", "lucia-fontes"})]), 2)

    def test_juntar_variantes_e_ignorar(self):
        g, nomes, _ = graph()
        self.assertIn("e-construtora-alfa", nomes)
        self.assertNotIn("e-alfa", nomes)
        self.assertFalse([n for n in g["nodes"] if "Defesa" in n[1] or n[1] == "Quaest"])

    def test_casos_e_pessoas(self):
        _, nomes, _ = graph()
        self.assertIn("e-cpi-do-asfalto", nomes)
        self.assertIn("e-rui-camargo", nomes)

    def test_limites_filtram(self):
        baixo, _, _ = graph()
        alto, _, _ = graph(min_news=3, min_link=2)
        self.assertLess(len(alto["links"]), len(baixo["links"]))

    def test_lista_grande_e_pulada(self):
        g, _, _ = graph(max_part=3)
        self.assertGreater(g["stats"]["puladas_por_lista"], 0)

    def test_toda_ligacao_tem_prova(self):
        g, _, _ = graph()
        for _, _, ev in g["links"]:
            self.assertTrue(ev)
            for i in ev:
                self.assertTrue(g["news"][i][3].startswith("http"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
