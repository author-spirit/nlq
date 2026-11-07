from nlq import history


def test_snapshot_keeps_the_first_200_rows():
    rows = [[index] for index in range(250)]
    report_id = history.save(
        {
            "question": "top orders",
            "title": "Top orders",
            "sql": "SELECT 1",
            "chart": {"type": "bar", "x": "label", "y": ["amount"], "series": None},
            "assumptions": ["Highest total_amount."],
            "rows": rows,
            "columns": ["n"],
            "row_count": 250,
            "answer_type": "sql",
            "status": "ok",
        }
    )
    listed = history.list_reports()
    assert listed[0]["id"] == report_id
    assert listed[0]["question"] == "top orders"
    opened = history.get_report(report_id)
    assert len(opened["rows"]) == 200
    assert opened["rows"][0] == [0]
    assert opened["chart"]["type"] == "bar"
    assert opened["columns"] == ["n"]
