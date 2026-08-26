"""
Integration test for Structuring, JSON Formulation, and Document Store.
"""
import unittest
import json
from pathlib import Path
import tempfile
import pandas as pd

from modules.structuring.json_builder import JSONStructureBuilder
from modules.storage.doc_store import DocumentStore


class TestStructuringAndDocStore(unittest.TestCase):

    def test_table_json_structuring_and_text_representation(self):
        builder = JSONStructureBuilder()

        # Simulated extracted document
        mock_doc = {
            "dokumen_id": "33210_2026_01",
            "dokumen_sumber": "Kabupaten Demak Dalam Angka 2026",
            "daerah": "Kabupaten Demak",
            "kategori": "Kependudukan",
            "tanggal_publikasi": "2026-02-28",
            "tahun": "2026",
            "tabel_list": [
                {
                    "tabel_id": "p45_t1",
                    "halaman": 45,
                    "judul_tabel": "Tabel 3.1.1 Jumlah Penduduk Menurut Jenis Kelamin dan Kecamatan di Kabupaten Demak",
                    "satuan": "Jiwa",
                    "sumber": "BPS Kabupaten Demak",
                    "catatan": "Data semester II",
                    "kolom": ["Kecamatan", "Jumlah_Penduduk_Laki-laki", "Jumlah_Penduduk_Perempuan", "Total"],
                    "records": [
                        {
                            "Kecamatan": "Mranggen",
                            "Jumlah_Penduduk_Laki-laki": 105432,
                            "Jumlah_Penduduk_Perempuan": 104521,
                            "Total": 209953
                        },
                        {
                            "Kecamatan": "Sayung",
                            "Jumlah_Penduduk_Laki-laki": 54120,
                            "Jumlah_Penduduk_Perempuan": 53900,
                            "Total": 108020
                        }
                    ]
                }
            ],
            "teks_list": [
                {
                    "halaman": 12,
                    "bab": "BAB 3 KEPENDUDUKAN",
                    "sub_bab": "3.1 Pertumbuhan Penduduk",
                    "teks": "Laju pertumbuhan penduduk Kabupaten Demak pada periode 2020-2025 tercatat sebesar 1,12 persen per tahun."
                }
            ]
        }

        chunks = builder.build_rag_chunks_from_extraction(mock_doc)
        
        # We expect 2 table rows + 1 narrative text = 3 chunks
        self.assertEqual(len(chunks), 3)

        # Verify Table Chunk #1
        row1 = chunks[0]
        self.assertEqual(row1["tipe_konten"], "tabel_baris")
        self.assertEqual(row1["daerah"], "Kabupaten Demak")
        self.assertEqual(row1["tahun"], "2026")
        self.assertEqual(row1["kategori"], "Kependudukan")
        self.assertIn("Mranggen", row1["representasi_teks"])
        self.assertIn("105.432 Jiwa", row1["representasi_teks"])
        self.assertIn("Kabupaten Demak Dalam Angka 2026", row1["representasi_teks"])

        # Verify Narrative Chunk #3
        narrative = chunks[2]
        self.assertEqual(narrative["tipe_konten"], "teks_naratif")
        self.assertEqual(narrative["bab"], "BAB 3 KEPENDUDUKAN")
        self.assertIn("Laju pertumbuhan penduduk", narrative["representasi_teks"])

        # Test Document DB persistence
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db_path = Path(tmpdir) / "test_doc_store.json"
            doc_store = DocumentStore(storage_path=temp_db_path)
            
            doc_store.save_document(
                doc_id=mock_doc["dokumen_id"],
                doc_metadata={
                    "dokumen_sumber": mock_doc["dokumen_sumber"],
                    "daerah": mock_doc["daerah"],
                    "tahun": mock_doc["tahun"]
                },
                chunks=chunks
            )

            retrieved = doc_store.get_document(mock_doc["dokumen_id"])
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["total_chunks"], 3)
            self.assertEqual(len(doc_store.list_documents()), 1)


if __name__ == "__main__":
    unittest.main()
