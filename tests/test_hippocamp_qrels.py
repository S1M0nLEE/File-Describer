"""HippoCamp 标注拆分测试。"""

from src.evaluation.hippocamp_qrels import extract_hippocamp_files, split_direct_indirect


def test_split_direct_indirect_single_file():
    item = {
        "file_path": ["contractnli/Tazza-CAFFE-Confidentiality-Agreement.pdf"],
        "evidence": [
            {"file_path": "contractnli/Tazza-CAFFE-Confidentiality-Agreement.pdf"},
        ],
    }
    direct, indirect = split_direct_indirect(item)
    assert direct == ["Tazza-CAFFE-Confidentiality-Agreement.pdf"]
    assert indirect == []


def test_split_direct_indirect_multi_file():
    item = {
        "file_path": [
            "a.pdf",
            "b.pdf",
            "c.pdf",
            "d.pdf",
        ],
        "evidence": [{"file_path": "a.pdf"}, {"file_path": "b.pdf"}],
    }
    direct, indirect = split_direct_indirect(item, max_direct=2)
    assert direct == ["a.pdf", "b.pdf"]
    assert set(indirect) == {"c.pdf", "d.pdf"}
    assert len(extract_hippocamp_files(item)) == 4
