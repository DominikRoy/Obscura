"""Trusted dealer deliveries, indexed locally before any online measurements."""

import contextlib
import os
import pickle
import sqlite3

from material import offline_groups

FORMAT = "obscura-paper-role-v2"
COMMON = "split,number,mode,slot,masked_x"
EXTRA = {"drone": "label,expected,y,seed0,drone_input", "wd": "seed1,corr,peer_auth"}


def generate(key_path, destination, limit):
    key = key_path.read_bytes()
    campaign = os.urandom(16).hex()
    destination.mkdir(mode=0o700)
    with contextlib.ExitStack() as stack:
        outputs = {}
        for role in EXTRA:
            path = destination / (role + ".pkl")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            stream = stack.enter_context(os.fdopen(fd, "wb"))
            pickle.dump((FORMAT, role, campaign), stream, protocol=4)
            outputs[role] = stream
        for split, group, mode, rows, box in offline_groups(key, limit):
            drone_rows, wd_rows = [], []
            for (
                dataset,
                number,
                setting,
                label,
                expected,
                probe,
                slot,
                mx,
                drone_shares,
                wd_masks,
                corr,
                mask,
                auth,
            ) in rows:
                common = (dataset, number, setting, slot, mx)
                drone_rows.append(common + (label, expected, probe, drone_shares, mask))
                wd_rows.append(common + (wd_masks, corr, auth))
            pickle.dump(
                (drone_rows, (split, group.start, mode, box)),
                outputs["drone"],
                protocol=4,
            )
            pickle.dump((wd_rows, None), outputs["wd"], protocol=4)
        for stream in outputs.values():
            pickle.dump(None, stream, protocol=4)


class DataReader(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError("Role files contain only built-in data")


def open_role(path, role):
    db = sqlite3.connect(":memory:")
    try:
        with path.open("rb") as stream, db:
            fmt, owner, campaign = DataReader(stream).load()
            if fmt not in ("obscura-paper-role-v1", FORMAT) or owner != role:
                raise ValueError("Incorrect role delivery")
            db.execute("CREATE TABLE info(role,campaign)")
            db.execute("INSERT INTO info VALUES(?,?)", (role, campaign))
            columns = COMMON + "," + EXTRA[role]
            db.execute(
                f"CREATE TABLE material({columns}, PRIMARY KEY(split,mode,number))"
            )
            marks = ",".join("?" for _ in columns.split(","))
            if role == "drone":
                db.execute(
                    "CREATE TABLE batches(split,first,mode,box, PRIMARY KEY(split,first,mode))"
                )
            while True:
                record = DataReader(stream).load()
                if record is None:
                    break
                rows, batch = record
                db.executemany(f"INSERT INTO material VALUES({marks})", rows)
                if role == "drone":
                    db.execute("INSERT INTO batches VALUES(?,?,?,?)", batch)
            if stream.read(1):
                raise ValueError("Unexpected data after role delivery")
        db.execute("PRAGMA query_only=ON")
        return db
    except BaseException:
        db.close()
        raise
