"""四个分类维度的 GROUP BY 视图。"""


def _seed(client):
    client.post("/api/v1/papers", json={"title": "A1", "first_author": "Alice", "corresponding_author": "Carol", "subject": "CV", "year": 2020, "doi": "10.1/a1"})
    client.post("/api/v1/papers", json={"title": "A2", "first_author": "Alice", "corresponding_author": "Dave", "subject": "NLP", "year": 2021, "doi": "10.1/a2"})
    client.post("/api/v1/papers", json={"title": "B1", "first_author": "Bob", "corresponding_author": "Carol", "subject": "CV", "year": 2020, "doi": "10.1/b1"})
    client.post("/api/v1/papers", json={"title": "N1", "first_author": None, "subject": None, "year": None, "doi": "10.1/n1"})


def test_groups_year(client):
    _seed(client)
    r = client.get("/api/v1/papers/groups/year")
    groups = {g["label"]: g["count"] for g in r.json()["data"]["groups"]}
    assert groups == {"2021": 1, "2020": 2, "未分类": 1}
    # 年份降序
    labels = [g["label"] for g in r.json()["data"]["groups"]]
    assert labels.index("2021") < labels.index("2020")


def test_groups_subject(client):
    _seed(client)
    groups = {g["label"]: g["count"] for g in client.get("/api/v1/papers/groups/subject").json()["data"]["groups"]}
    assert groups == {"CV": 2, "NLP": 1, "未分类": 1}


def test_groups_first_author(client):
    _seed(client)
    groups = {g["label"]: g["count"] for g in client.get("/api/v1/papers/groups/first_author").json()["data"]["groups"]}
    assert groups == {"Alice": 2, "Bob": 1, "未分类": 1}


def test_groups_corresponding_author(client):
    _seed(client)
    groups = {g["label"]: g["count"] for g in client.get("/api/v1/papers/groups/corresponding_author").json()["data"]["groups"]}
    assert groups == {"Carol": 2, "Dave": 1, "未分类": 1}


def test_groups_unknown_dimension(client):
    assert client.get("/api/v1/papers/groups/foo").status_code == 404
