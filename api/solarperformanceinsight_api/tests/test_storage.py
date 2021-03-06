import datetime as dt
import uuid


from fastapi import HTTPException
import pandas as pd
import pymysql
import pytest


from solarperformanceinsight_api import storage


@pytest.fixture(scope="module")
def storage_interface(auth0_id):
    out = storage.StorageInterface()
    out.commit = False
    out.user = auth0_id
    return out


def test_escape_timestamp():
    assert (
        storage.escape_timestamp(pd.Timestamp("2019-04-08T030423"))
        == "'2019-04-08 03:04:23'"
    )
    assert (
        storage.escape_timestamp(pd.Timestamp("2019-04-08T030423Z"))
        == "'2019-04-08 03:04:23'"
    )
    assert (
        storage.escape_timestamp(pd.Timestamp("2019-04-08T030423-0300"))
        == "'2019-04-08 06:04:23'"
    )


def test_escape_datetime():
    assert (
        storage.escape_datetime(dt.datetime(2019, 5, 1, 23, 33, 12))
        == "'2019-05-01 23:33:12'"
    )
    assert (
        storage.escape_datetime(
            dt.datetime(
                2019, 5, 1, 23, 33, 12, tzinfo=dt.timezone(dt.timedelta(hours=-5))
            )
        )
        == "'2019-05-02 04:33:12'"
    )


def test_convert_datetime_utc():
    assert storage.convert_datetime_utc("2019-05-01 23:01:32") == dt.datetime(
        2019, 5, 1, 23, 1, 32, tzinfo=dt.timezone(dt.timedelta(hours=0))
    )


def test_no_cursor(storage_interface):
    with pytest.raises(AttributeError):
        storage_interface.cursor


@pytest.mark.parametrize("err", [pymysql.err.OperationalError, HTTPException])
def test_start_transaction_rollback(mocker, err):
    si = storage.StorageInterface()
    conn = mocker.MagicMock()
    mocker.patch.object(storage.engine, "connect", return_value=conn)

    with pytest.raises(err):
        with si.start_transaction():
            raise err(400)
    conn.rollback.assert_called()
    conn.commit.assert_not_called()


def test_start_transaction_commit(mocker):
    si = storage.StorageInterface()
    conn = mocker.MagicMock()
    mocker.patch.object(storage.engine, "connect", return_value=conn)
    with si.start_transaction() as st:
        st.cursor.execute("select 1")
    conn.commit.assert_called()


def test_start_transaction_no_commit(mocker):
    si = storage.StorageInterface()
    si.commit = False
    conn = mocker.MagicMock()
    mocker.patch.object(storage.engine, "connect", return_value=conn)
    with si.start_transaction() as st:
        st.cursor.execute("select 1")
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


@pytest.mark.parametrize(
    "errno,outerr,status_code",
    [
        (1142, HTTPException, 404),
        (1062, HTTPException, 409),
        (3140, HTTPException, 400),
        (1406, HTTPException, 400),
        (1048, HTTPException, 400),
        (1408, pymysql.err.OperationalError, None),
    ],
)
def test_try_query_raises(storage_interface, errno, outerr, status_code):
    with pytest.raises(outerr) as err:
        with storage_interface.start_transaction() as st:
            st.try_query(
                "signal sqlstate '45000' set message_text='',"
                f" mysql_errno = {errno}",
                None,
            )
    if status_code:
        err.value.status_code == status_code


def test_timezone(storage_interface):
    with storage_interface.start_transaction() as st:
        st.cursor.execute("SELECT @@session.time_zone as tz")
        res = st.cursor.fetchone()["tz"]
    assert res == "+00:00"


def test_call_procedure(storage_interface, mocker, auth0_id):
    tryq = mocker.patch.object(storage_interface, "try_query")
    with storage_interface.start_transaction() as st:
        st._cursor = mocker.MagicMock()
        st._call_procedure("the_procedure", 0, "a")
    tryq.assert_called_with("CALL the_procedure(%s,%s,%s)", (auth0_id, 0, "a"))


def test_call_procedure_without_user(storage_interface, mocker):
    tryq = mocker.patch.object(storage_interface, "try_query")
    with storage_interface.start_transaction() as st:
        st._cursor = mocker.MagicMock()
        st._call_procedure("the_procedure", 0, "a", with_current_user=False)
    tryq.assert_called_with("CALL the_procedure(%s,%s)", (0, "a"))


def test_call_procedure_for_single(storage_interface, mocker):
    callp = mocker.patch.object(storage_interface, "_call_procedure", return_value=[0])
    with storage_interface.start_transaction() as st:
        out = st._call_procedure_for_single("the_procedure", 0, "a")
    callp.assert_called()
    assert out == 0


def test_call_procedure_for_single_nothing(storage_interface, mocker):
    mocker.patch.object(storage_interface, "_call_procedure", return_value=[])
    with pytest.raises(HTTPException):
        with storage_interface.start_transaction() as st:
            st._call_procedure_for_single("the_procedure", 0, "a")


def test_delete_system(storage_interface, add_example_db_data, system_id):
    with storage_interface.start_transaction() as st:
        st.delete_system(system_id)
        assert len(st.list_systems()) == 0


def test_delete_system_dne(storage_interface, add_example_db_data):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.delete_system(uuid.uuid1())
    assert err.value.status_code == 404


def test_delete_system_wrong_owner(
    storage_interface, add_example_db_data, other_system_id
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.delete_system(other_system_id)
    assert err.value.status_code == 404


def test_create_system(storage_interface, add_example_db_data, system_def):
    system_def.name = "New System"
    with storage_interface.start_transaction() as st:
        sysid = st.create_system(system_def)
        out = st.get_system(sysid.object_id)
    assert out.definition == system_def


def test_create_system_duplicate(storage_interface, add_example_db_data, system_def):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.create_system(system_def)
    assert err.value.status_code == 409


def test_list_system(storage_interface, add_example_db_data, stored_system):
    with storage_interface.start_transaction() as st:
        out = st.list_systems()
    assert out == [stored_system]


def test_get_system(storage_interface, add_example_db_data, stored_system, system_id):
    with storage_interface.start_transaction() as st:
        out = st.get_system(system_id)
    assert out == stored_system


def test_get_system_dne(storage_interface, add_example_db_data):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_system(uuid.uuid1())
    assert err.value.status_code == 404


def test_get_system_wrong_owner(
    storage_interface, add_example_db_data, other_system_id
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_system(other_system_id)
    assert err.value.status_code == 404


@pytest.mark.parametrize("alter", [0, 1])
def test_update_system(
    storage_interface, add_example_db_data, stored_system, system_id, system_def, alter
):
    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc, microsecond=0)
    if alter:
        system_def.elevation = 999
        system_def.inverters[0].arrays[0].strings = 3
    with storage_interface.start_transaction() as st:
        st.update_system(system_id, system_def)
        out = st.get_system(system_id)
    assert out.definition == system_def
    assert out.created_at == stored_system.created_at
    assert out.modified_at >= now


def test_update_system_dne(storage_interface, add_example_db_data, system_def):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.update_system(uuid.uuid1(), system_def)
    assert err.value.status_code == 404


def test_update_system_wrong_owner(
    storage_interface, add_example_db_data, other_system_id, system_def
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.update_system(other_system_id, system_def)
    assert err.value.status_code == 404


def test_create_user_if_not_exists(storage_interface, add_example_db_data, mocker):
    now = dt.datetime.utcnow().replace(microsecond=0, tzinfo=dt.timezone.utc)
    mocker.patch.object(storage_interface, "user", new="newuser")
    with storage_interface.start_transaction() as st:
        st.create_user_if_not_exists()
        out = st._call_procedure_for_single("get_user")
    assert out["created_at"] >= now
    assert out["auth0_id"] == "newuser"


def test_create_user_if_not_exists_does_already(
    storage_interface, add_example_db_data, auth0_id
):
    with storage_interface.start_transaction() as st:
        st.create_user_if_not_exists()
        out = st._call_procedure_for_single("get_user")
    assert out["created_at"] == dt.datetime(2020, 12, 1, 1, 23, tzinfo=dt.timezone.utc)
    assert out["auth0_id"] == auth0_id


def test_get_user(storage_interface, add_example_db_data, auth0_id, user_id):
    with storage_interface.start_transaction() as st:
        out = st.get_user()
    assert out.created_at == dt.datetime(2020, 12, 1, 1, 23, tzinfo=dt.timezone.utc)
    assert out.auth0_id == auth0_id
    assert out.object_id == user_id
    assert out.object_type == "user"
    assert out.modified_at == out.created_at


@pytest.fixture()
def cleanup_user(root_conn):
    try:
        yield
    finally:
        curs = root_conn.cursor()
        curs.execute("delete from users where auth0_id = 'newuser'")
        root_conn.commit()


def test_get_user_new(storage_interface, mocker, cleanup_user):
    now = dt.datetime.utcnow().replace(microsecond=0, tzinfo=dt.timezone.utc)
    mocker.patch.object(storage_interface, "user", new="newuser")
    create = mocker.spy(storage_interface, "create_user_if_not_exists")
    with storage_interface.start_transaction() as st:
        out = st.get_user()
    assert out.created_at >= now
    assert out.auth0_id == "newuser"
    assert out.object_type == "user"
    create.assert_called()


def test_create_job(storage_interface, add_example_db_data, job_def):
    with storage_interface.start_transaction() as st:
        sysid = st.create_job(job_def)
        out = st.get_job(sysid.object_id)
    assert out.definition == job_def


def test_list_job(storage_interface, add_example_db_data, stored_job, complete_job_id):
    with storage_interface.start_transaction() as st:
        out = st.list_jobs()
    assert out[0] == stored_job
    assert len(out) == 5
    assert str(out[1].object_id) == complete_job_id


def test_get_job(storage_interface, add_example_db_data, stored_job, job_id):
    with storage_interface.start_transaction() as st:
        out = st.get_job(job_id)
    assert out == stored_job


def test_get_job_dne(storage_interface, add_example_db_data):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_job(uuid.uuid1())
    assert err.value.status_code == 404


def test_get_job_wrong_owner(storage_interface, add_example_db_data, other_job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_job(other_job_id)
    assert err.value.status_code == 404


def test_delete_job(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        before = st.list_jobs()
        assert len(before) == 5
        assert str(before[0].object_id) == job_id
        st.delete_job(job_id)
        after = st.list_jobs()
        assert len(after) == 4
        assert str(after[0].object_id) != job_id


def test_delete_job_dne(storage_interface, add_example_db_data):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.delete_job(uuid.uuid1())
    assert err.value.status_code == 404


def test_delete_job_wrong_owner(storage_interface, add_example_db_data, other_job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.delete_job(other_job_id)
    assert err.value.status_code == 404


def test_get_job_status(storage_interface, add_example_db_data, job_id, job_status):
    with storage_interface.start_transaction() as st:
        stat = st.get_job_status(job_id)
    assert stat == job_status


def test_get_job_status_dne(storage_interface, add_example_db_data):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_job_status(uuid.uuid1())
    assert err.value.status_code == 404


def test_get_job_status_wrong_owner(
    storage_interface, add_example_db_data, other_job_id
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_job_status(other_job_id)
    assert err.value.status_code == 404


def test_get_job_data(
    storage_interface,
    add_example_db_data,
    job_data_ids,
    job_data_meta,
    job_id,
    arrow_job_data,
):
    with storage_interface.start_transaction() as st:
        data = st.get_job_data(job_id, job_data_ids[1])
    job_data_meta.definition.data_columns = []
    assert data == (job_data_meta, arrow_job_data)


def test_get_job_data_empty(
    storage_interface, add_example_db_data, job_data_ids, job_data_meta, job_id
):
    with storage_interface.start_transaction() as st:
        data = st.get_job_data(job_id, job_data_ids[0])
    assert data[1] is None
    assert data[0].definition.filename == ""
    assert not data[0].definition.present


def test_get_job_data_dne(storage_interface, add_example_db_data, job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.get_job_data(job_id, job_id)
    assert err.value.status_code == 404


def test_add_job_data(storage_interface, add_example_db_data, job_data_ids, job_id):
    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc, microsecond=0)
    with storage_interface.start_transaction() as st:
        st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"new data")
        newd = st.get_job_data(job_id, job_data_ids[0])
        stat = st.get_job_status(job_id)
    assert newd[0].definition.filename == "newfname"
    assert newd[0].modified_at >= now
    assert newd[1] == b"new data"
    assert newd[0].definition.present
    assert stat.status == "prepared"
    assert stat.last_change >= now
    with storage_interface.start_transaction() as st:
        st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"more newer data")


def test_add_job_data_dne(storage_interface, add_example_db_data, job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.add_job_data(job_id, job_id, "newfname", "text", b"new data")
    assert err.value.status_code == 404


@pytest.fixture()
def mark_job_complete(root_conn, job_id):
    curs = root_conn.cursor()
    curs.execute(
        "update jobs set status = 'complete' where id = uuid_to_bin(%s, 1)", job_id
    )
    root_conn.commit()
    yield
    curs.execute(
        "update jobs set status = 'created' where id = uuid_to_bin(%s, 1)", job_id
    )
    root_conn.commit()


def test_add_job_data_after_queued(
    storage_interface, add_example_db_data, job_id, job_data_ids
):
    with storage_interface.start_transaction() as st:
        st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"new data")
        st.queue_job(job_id)
        stat = st.get_job_status(job_id)
        assert stat.status == "queued"
        with pytest.raises(HTTPException) as err:
            st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"new data")
        assert err.value.status_code == 409


def test_add_job_data_after_complete(
    storage_interface, add_example_db_data, job_data_ids, mark_job_complete, job_id
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"new data")
    assert err.value.status_code == 409


def test_queue_job(storage_interface, add_example_db_data, job_data_ids, job_id):
    with storage_interface.start_transaction() as st:
        st.add_job_data(job_id, job_data_ids[0], "newfname", "text", b"new data")
        st.queue_job(job_id)
        out = st.get_job_status(job_id)
    assert out.status == "queued"


def test_queue_job_dne(storage_interface, add_example_db_data, other_job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.queue_job(other_job_id)
    assert err.value.status_code == 404


def test_queue_job_incomplete(storage_interface, add_example_db_data, job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.queue_job(job_id)
    assert err.value.status_code == 400


def test_queue_job_already_complete(
    storage_interface, add_example_db_data, job_id, mark_job_complete
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.queue_job(job_id)
    assert err.value.status_code == 409


def test_list_job_results(
    storage_interface, complete_job_id, job_result_list, add_example_db_data
):
    with storage_interface.start_transaction() as st:
        res = st.list_job_results(complete_job_id)
    assert res == job_result_list


def test_list_job_results_not_done(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        res = st.list_job_results(job_id)
    assert res == []


def test_list_job_results_dne(storage_interface, add_example_db_data, other_job_id):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            st.list_job_results(other_job_id)
    assert err.value.status_code == 404


def test_get_job_result(
    storage_interface,
    add_example_db_data,
    complete_job_id,
    job_result_ids,
    job_result_list,
    arrow_performance_job_result,
    arrow_weather_job_result,
):
    for i, id_ in enumerate(job_result_ids):
        with storage_interface.start_transaction() as st:
            res, data = st.get_job_result(complete_job_id, id_)
        assert res == job_result_list[i]
        if i > 0:
            assert data == arrow_performance_job_result
        else:
            assert data == arrow_weather_job_result


def test_get_job_result_dne(
    storage_interface, add_example_db_data, job_id, job_result_ids
):
    with pytest.raises(HTTPException) as err:
        with storage_interface.start_transaction() as st:
            res, data = st.get_job_result(job_id, job_result_ids[0])
    assert err.value.status_code == 404


def test_add_job_result_complete(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        newid = st.add_job_result(job_id, "/", "performance data", "text/csv", b"")
        st.set_job_complete(job_id)

        job_results = st.list_job_results(job_id)
        status = st.get_job_status(job_id)

    assert newid.object_id == job_results[0].object_id
    assert status.status == "complete"


def test_add_job_result_error(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        newid = st.add_job_result(job_id, "/", "error message", "application/json", b"")
        st.set_job_error(job_id)

        job_results = st.list_job_results(job_id)
        status = st.get_job_status(job_id)

    assert newid.object_id == job_results[0].object_id
    assert status.status == "error"


def test_add_job_result_no_status_update(
    storage_interface, add_example_db_data, job_id
):
    with pytest.raises(storage.StorageTransactionError):
        with storage_interface.start_transaction() as st:
            st.add_job_result(job_id, "/", "performance data", "text/csv", b"")


def test_add_job_result_already_complete(
    storage_interface, add_example_db_data, complete_job_id
):
    with pytest.raises(storage.JobAlreadyComplete):
        with storage_interface.start_transaction() as st:
            st.add_job_result(complete_job_id, "/", "performance data", "text/csv", b"")


def test_add_job_result_dne(storage_interface, add_example_db_data):
    with pytest.raises(storage.JobResultFailure):
        with storage_interface.start_transaction() as st:
            st.add_job_result(uuid.uuid1(), "/", "performance data", "text/csv", b"")


def test_add_job_bad_data(storage_interface, add_example_db_data, job_id):
    with pytest.raises(storage.JobResultFailure):
        with storage_interface.start_transaction() as st:
            st.add_job_result(job_id, "/", "performance data" * 100, "text/csv", "")


def test_set_job_complete(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        before = st.get_job_status(job_id)
        st.set_job_complete(job_id)
        after = st.get_job_status(job_id)
    assert before.status != "complete"
    assert after.status == "complete"


def test_set_job_complete_dne(storage_interface, add_example_db_data):
    with pytest.raises(storage.JobResultFailure):
        with storage_interface.start_transaction() as st:
            st.set_job_complete(uuid.uuid1())


def test_set_job_error(storage_interface, add_example_db_data, job_id):
    with storage_interface.start_transaction() as st:
        before = st.get_job_status(job_id)
        st.set_job_error(job_id)
        after = st.get_job_status(job_id)
    assert before.status != "error"
    assert after.status == "error"


def test_set_job_error_dne(storage_interface, add_example_db_data):
    with pytest.raises(storage.JobResultFailure):
        with storage_interface.start_transaction() as st:
            st.set_job_error(uuid.uuid1())


@pytest.fixture()
def job_managment_interface(auth0_id, mocker):
    mocker.patch(
        "solarperformanceinsight_api.storage.engine",
        new=storage.create_engine(
            "mysql+pymysql://",
            creator=storage._make_sql_connection_partial(user="qmanager"),
        ).pool,
    )
    out = storage.JobManagementInterface()
    out.commit = False
    return out


def test_list_status_of_jobs(
    job_managment_interface,
    add_example_db_data,
    job_id,
    complete_job_id,
    other_job_id,
    weatherpr_job_id,
    refvsactual_job_id,
    monthlypa_job_id,
):
    out = job_managment_interface.list_status_of_jobs()
    assert out == {
        job_id: "created",
        other_job_id: "created",
        complete_job_id: "complete",
        weatherpr_job_id: "created",
        refvsactual_job_id: "created",
        monthlypa_job_id: "created",
    }


@pytest.fixture()
def set_job_queued(job_id, root_conn):
    curs = root_conn.cursor()
    curs.execute(
        "update jobs set status = 'queued' where id = uuid_to_bin(%s, 1)", job_id
    )
    root_conn.commit()
    yield
    curs.execute(
        "update jobs set status = 'created' where id = uuid_to_bin(%s, 1)", job_id
    )
    root_conn.commit()


def test_list_queued_jobs(
    job_managment_interface, add_example_db_data, job_id, auth0_id, set_job_queued
):
    assert job_managment_interface.list_queued_jobs() == {job_id: auth0_id}


def test_list_queued_jobs_none(
    job_managment_interface, add_example_db_data, job_id, auth0_id
):
    assert job_managment_interface.list_queued_jobs() == {}


def test_report_job_failure(
    job_managment_interface, add_example_db_data, job_id, root_conn
):
    job_managment_interface.commit = True
    msg = '{"message": "much fail"}'
    new_id = job_managment_interface.report_job_failure(job_id, msg)
    curs = root_conn.cursor()
    curs.execute("select data from job_results where id = uuid_to_bin(%s, 1)", new_id)
    assert curs.fetchone()[0] == msg.encode()
    curs.execute("delete from job_results where id = uuid_to_bin(%s, 1)", new_id)
    root_conn.commit()
