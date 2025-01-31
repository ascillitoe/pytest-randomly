from __future__ import annotations

from unittest import mock

import pytest

import pytest_randomly

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def reset_entrypoints_cache():
    yield
    pytest_randomly.entrypoint_reseeds = None


@pytest.fixture
def ourtestdir(testdir):
    testdir.tmpdir.join("pytest.ini").write(
        "[pytest]\n" "console_output_style = classic"
    )

    # Change from default running pytest in-process to running in a subprocess
    # because numpy imports break with weird:
    #   File ".../site-packages/numpy/core/overrides.py", line 204, in decorator
    # add_docstring(implementation, dispatcher.__doc__)
    # RuntimeError: empty_like method already has a docstring
    # testdir._runpytest_method = testdir.runpytest_subprocess

    yield testdir


@pytest.fixture
def simpletestdir(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            assert True
        """
    )
    yield ourtestdir


def test_it_reports_a_header_when_not_set(simpletestdir):
    out = simpletestdir.runpytest()
    assert len([x for x in out.outlines if x.startswith("Using --randomly-seed=")]) == 1


def test_it_reports_a_header_when_set(simpletestdir):
    out = simpletestdir.runpytest("--randomly-seed=10")
    lines = [x for x in out.outlines if x.startswith("Using --randomly-seed=")]
    assert lines == ["Using --randomly-seed=10"]


def test_it_reuses_the_same_random_seed_per_test(ourtestdir):
    """
    Run a pair of tests that generate the a number and then assert they got
    what the other did.
    """
    ourtestdir.makepyfile(
        test_one="""
        import random

        def test_a():
            test_a.num = random.random()
            if hasattr(test_b, 'num'):
                assert test_a.num == test_b.num

        def test_b():
            test_b.num = random.random()
            if hasattr(test_a, 'num'):
                assert test_b.num == test_a.num
        """
    )
    out = ourtestdir.runpytest("--randomly-dont-reorganize")
    out.assert_outcomes(passed=2, failed=0)


def test_without_cacheprovider(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            pass
        """
    )
    out = ourtestdir.runpytest("-p", "no:cacheprovider")
    out.assert_outcomes(passed=1, failed=0)


def test_using_last_seed(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            pass
        """
    )
    out = ourtestdir.runpytest()
    out.assert_outcomes(passed=1, failed=0)
    seed_line = [x for x in out.stdout.lines if x.startswith("Using --randomly-seed=")][
        0
    ]

    out = ourtestdir.runpytest("--randomly-seed=last")
    out.assert_outcomes(passed=1, failed=0)
    out.stdout.fnmatch_lines([seed_line])


def test_using_last_explicit_seed(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            pass
        """
    )
    out = ourtestdir.runpytest("--randomly-seed=33")
    out.assert_outcomes(passed=1, failed=0)
    out.stdout.fnmatch_lines(["Using --randomly-seed=33"])

    out = ourtestdir.runpytest("--randomly-seed=last")
    out.assert_outcomes(passed=1, failed=0)
    out.stdout.fnmatch_lines(["Using --randomly-seed=33"])


def test_passing_nonsense_for_randomly_seed(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            pass
        """
    )
    out = ourtestdir.runpytest("--randomly-seed=invalidvalue")
    assert out.ret != 0
    out.stderr.fnmatch_lines(
        [
            (
                "*: error: argument --randomly-seed: 'invalidvalue' "
                + "is not an integer or the string 'last'"
            )
        ]
    )


def test_it_resets_the_random_seed_at_the_start_of_test_classes(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random
        from unittest import TestCase


        class A(TestCase):

            @classmethod
            def setUpClass(cls):
                super(A, cls).setUpClass()
                cls.suc_num = random.random()
                assert cls.suc_num == getattr(B, 'suc_num', cls.suc_num)

            def test_fake(self):
                assert True


        class B(TestCase):

            @classmethod
            def setUpClass(cls):
                super(B, cls).setUpClass()
                cls.suc_num = random.random()
                assert cls.suc_num == getattr(A, 'suc_num', cls.suc_num)

            def test_fake(self):
                assert True
        """
    )
    out = ourtestdir.runpytest()
    out.assert_outcomes(passed=2, failed=0)


def test_it_resets_the_random_seed_at_the_end_of_test_classes(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random
        from unittest import TestCase


        class A(TestCase):

            def test_fake(self):
                assert True

            @classmethod
            def tearDownClass(cls):
                super(A, cls).tearDownClass()
                cls.suc_num = random.random()
                assert cls.suc_num == getattr(B, 'suc_num', cls.suc_num)


        class B(TestCase):

            def test_fake(self):
                assert True

            @classmethod
            def tearDownClass(cls):
                super(B, cls).tearDownClass()
                cls.suc_num = random.random()
                assert cls.suc_num == getattr(A, 'suc_num', cls.suc_num)
        """
    )
    out = ourtestdir.runpytest()
    out.assert_outcomes(passed=2, failed=0)


def test_the_same_random_seed_per_test_can_be_turned_off(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random

        def test_a():
            test_a.state1 = random.getstate()
            assert test_a.state1 == random.getstate()  # sanity check
            assert random.random() >= 0  # mutate state
            test_a.state2 = random.getstate()

        def test_b():
            test_b.state = random.getstate()
            assert test_b.state == random.getstate()  # sanity check
            assert test_a.state1 != test_b.state
            assert test_a.state2 == test_b.state
        """
    )
    out = ourtestdir.runpytest(
        "--randomly-dont-reset-seed", "--randomly-dont-reorganize"
    )
    out.assert_outcomes(passed=2, failed=0)


def test_files_reordered(ourtestdir):
    code = """
        def test_it():
            pass
    """
    ourtestdir.makepyfile(test_a=code, test_b=code, test_c=code, test_d=code)
    args = ["-v", "--randomly-seed=15"]

    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_b.py::test_it PASSED",
        "test_a.py::test_it PASSED",
        "test_d.py::test_it PASSED",
        "test_c.py::test_it PASSED",
    ]


def test_files_reordered_when_seed_not_reset(ourtestdir):
    code = """
        def test_it():
            pass
    """
    ourtestdir.makepyfile(test_a=code, test_b=code, test_c=code, test_d=code)
    args = ["-v", "--randomly-seed=15"]

    args.append("--randomly-dont-reset-seed")
    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_b.py::test_it PASSED",
        "test_a.py::test_it PASSED",
        "test_d.py::test_it PASSED",
        "test_c.py::test_it PASSED",
    ]


def test_classes_reordered(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        from unittest import TestCase


        class A(TestCase):
            def test_a(self):
                pass


        class B(TestCase):
            def test_b(self):
                pass


        class C(TestCase):
            def test_c(self):
                pass


        class D(TestCase):
            def test_d(self):
                pass
        """
    )
    args = ["-v", "--randomly-seed=15"]

    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_one.py::D::test_d PASSED",
        "test_one.py::B::test_b PASSED",
        "test_one.py::C::test_c PASSED",
        "test_one.py::A::test_a PASSED",
    ]


def test_class_test_methods_reordered(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        from unittest import TestCase

        class T(TestCase):
            def test_a(self):
                pass

            def test_b(self):
                pass

            def test_c(self):
                pass

            def test_d(self):
                pass
        """
    )
    args = ["-v", "--randomly-seed=15"]

    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_one.py::T::test_c PASSED",
        "test_one.py::T::test_b PASSED",
        "test_one.py::T::test_a PASSED",
        "test_one.py::T::test_d PASSED",
    ]


def test_test_functions_reordered(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            pass

        def test_b():
            pass

        def test_c():
            pass

        def test_d():
            pass
        """
    )
    args = ["-v", "--randomly-seed=15"]

    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_one.py::test_c PASSED",
        "test_one.py::test_a PASSED",
        "test_one.py::test_b PASSED",
        "test_one.py::test_d PASSED",
    ]


def test_test_functions_reordered_when_randomness_in_module(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random
        import time

        random.seed(time.time() * 100)

        def test_a():
            pass

        def test_b():
            pass

        def test_c():
            pass

        def test_d():
            pass
        """
    )
    args = ["-v", "--randomly-seed=15"]

    out = ourtestdir.runpytest(*args)

    out.assert_outcomes(passed=4, failed=0)
    assert out.outlines[8:12] == [
        "test_one.py::test_c PASSED",
        "test_one.py::test_a PASSED",
        "test_one.py::test_b PASSED",
        "test_one.py::test_d PASSED",
    ]


def test_doctests_reordered(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def foo():
            '''
            >>> foo()
            9001
            '''
            return 9001

        def bar():
            '''
            >>> bar()
            9002
            '''
            return 9002
        """
    )
    args = ["-v", "--doctest-modules", "--randomly-seed=1"]

    out = ourtestdir.runpytest(*args)
    out.assert_outcomes(passed=2)
    assert out.outlines[8:10] == [
        "test_one.py::test_one.bar PASSED",
        "test_one.py::test_one.foo PASSED",
    ]


def test_it_works_with_the_simplest_test_items(ourtestdir):
    ourtestdir.makepyfile(
        conftest="""
        import sys

        import pytest


        class MyCollector(pytest.Collector):
            def __init__(self, fspath, items, **kwargs):
                super(MyCollector, self).__init__(fspath, **kwargs)
                self.items = items

            def collect(self):
                return self.items


        class NoOpItem(pytest.Item):
            def __init__(self, name, parent, module=None):
                super(NoOpItem, self).__init__(name=name, parent=parent)
                if module is not None:
                    self.module = module

            def runtest(self):
                pass


        def pytest_collect_file(path, parent):
            if not str(path).endswith('.py'):
                return
            return MyCollector.from_parent(
                parent=parent,
                fspath=str(path),
                items=[
                    NoOpItem.from_parent(
                        name=str(path) + "1",
                        parent=parent,
                        module=sys.modules[__name__],
                    ),
                    NoOpItem.from_parent(
                        name=str(path) + "1",
                        parent=parent,
                        module=sys.modules[__name__],
                    ),
                    NoOpItem.from_parent(
                        name=str(path) + "2",
                        parent=parent,
                    ),
                ],
            )
        """
    )
    args = ["-v"]

    out = ourtestdir.runpytest(*args)
    out.assert_outcomes(passed=3)


def test_doctests_in_txt_files_reordered(ourtestdir):
    ourtestdir.tmpdir.join("test.txt").write(
        """\
        >>> 2 + 2
        4
        """
    )
    ourtestdir.tmpdir.join("test2.txt").write(
        """\
        >>> 2 - 2
        0
        """
    )
    args = ["-v", "--randomly-seed=2"]

    out = ourtestdir.runpytest(*args)
    out.assert_outcomes(passed=2)
    assert out.outlines[8:10] == [
        "test2.txt::test2.txt PASSED",
        "test.txt::test.txt PASSED",
    ]


def test_it_runs_before_stepwise(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            assert 0


        def test_b():
            assert 0
        """
    )
    out = ourtestdir.runpytest("-v", "--randomly-seed=1", "--stepwise")
    out.assert_outcomes(failed=1)

    # Now make test_b pass
    ourtestdir.makepyfile(
        test_one="""
        def test_a():
            assert 0


        def test_b():
            assert 1
        """
    )
    ourtestdir.tmpdir.join("__pycache__").remove()
    out = ourtestdir.runpytest("-v", "--randomly-seed=1", "--stepwise")
    out.assert_outcomes(passed=1, failed=1)
    out = ourtestdir.runpytest("-v", "--randomly-seed=1", "--stepwise")
    out.assert_outcomes(failed=1)


def test_fixtures_get_different_random_state_to_tests(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random

        import pytest


        @pytest.fixture()
        def myfixture():
            return random.getstate()


        def test_one(myfixture):
            assert myfixture != random.getstate()
        """
    )
    out = ourtestdir.runpytest()
    out.assert_outcomes(passed=1)


def test_fixtures_dont_interfere_with_tests_getting_same_random_state(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import random

        import pytest


        random.seed(2)
        state_at_seed_two = random.getstate()


        @pytest.fixture(scope='module')
        def myfixture():
            return random.random()


        @pytest.mark.one()
        def test_one(myfixture):
            assert random.getstate() == state_at_seed_two


        @pytest.mark.two()
        def test_two(myfixture):
            assert random.getstate() == state_at_seed_two
        """
    )
    args = ["--randomly-seed=2"]

    out = ourtestdir.runpytest(*args)
    out.assert_outcomes(passed=2)

    out = ourtestdir.runpytest("-m", "one", *args)
    out.assert_outcomes(passed=1)
    out = ourtestdir.runpytest("-m", "two", *args)
    out.assert_outcomes(passed=1)


def test_factory_boy(ourtestdir):
    """
    Rather than set up factories etc., just check the random generator it uses
    is set between two tests to output the same number.
    """
    ourtestdir.makepyfile(
        test_one="""
        from factory.random import randgen

        def test_a():
            test_a.num = randgen.random()
            if hasattr(test_b, 'num'):
                assert test_a.num == test_b.num

        def test_b():
            test_b.num = randgen.random()
            if hasattr(test_a, 'num'):
                assert test_b.num == test_a.num
        """
    )

    out = ourtestdir.runpytest("--randomly-seed=1")
    out.assert_outcomes(passed=2)


def test_faker(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        from faker import Faker

        fake = Faker()

        def test_one():
            assert fake.name() == 'Ryan Gallagher'

        def test_two():
            assert fake.name() == 'Ryan Gallagher'
        """
    )

    out = ourtestdir.runpytest("--randomly-seed=1")
    out.assert_outcomes(passed=2)


def test_faker_fixture(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        def test_one(faker):
            assert faker.name() == 'Ryan Gallagher'

        def test_two(faker):
            assert faker.name() == 'Ryan Gallagher'
        """
    )

    out = ourtestdir.runpytest("--randomly-seed=1")
    out.assert_outcomes(passed=2)


def test_numpy(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import numpy as np

        def test_one():
            assert np.random.rand() == 0.417022004702574

        def test_two():
            assert np.random.rand() == 0.417022004702574
        """
    )

    out = ourtestdir.runpytest("--randomly-seed=1")
    out.assert_outcomes(passed=2)


def test_numpy_doesnt_crash_with_large_seed(ourtestdir):
    ourtestdir.makepyfile(
        test_one="""
        import numpy as np

        def test_one():
            assert np.random.rand() >= 0.0
        """
    )

    out = ourtestdir.runpytest("--randomly-seed=7106521602475165645")
    out.assert_outcomes(passed=1)


def test_failing_import(testdir):
    """Test with pytest raising CollectError or ImportError.

    This happens when trying to access item.module during
    pytest_collection_modifyitems.
    """
    modcol = testdir.getmodulecol("import alksdjalskdjalkjals")
    assert modcol.instance is None

    modcol = testdir.getmodulecol("pytest_plugins='xasdlkj',")
    with pytest.raises(ImportError):
        modcol.obj


def test_entrypoint_injection(pytester, monkeypatch):
    """Test that registered entry points are seeded"""
    (pytester.path / "test_one.py").write_text("def test_one(): pass\n")

    class _FakeEntryPoint:
        """Minimal surface of Entry point API to allow testing"""

        def __init__(self, name: str, obj: mock.Mock) -> None:
            self.name = name
            self._obj = obj

        def load(self) -> mock.Mock:
            return self._obj

    entry_points: list[_FakeEntryPoint] = []

    def fake_entry_points(*, group):
        return entry_points

    monkeypatch.setattr(pytest_randomly, "entry_points", fake_entry_points)
    reseed = mock.Mock()
    entry_points.append(_FakeEntryPoint("test_seeder", reseed))

    # Need to run in-process so that monkeypatching works
    pytester.runpytest_inprocess("--randomly-seed=1")
    assert reseed.mock_calls == [
        mock.call(1),
        mock.call(1),
        mock.call(0),
        mock.call(1),
        mock.call(2),
    ]

    reseed.mock_calls[:] = []
    pytester.runpytest_inprocess("--randomly-seed=424242")
    assert reseed.mock_calls == [
        mock.call(424242),
        mock.call(424242),
        mock.call(424241),
        mock.call(424242),
        mock.call(424243),
    ]


def test_entrypoint_missing(pytester, monkeypatch):
    """
    Test that if there aren't any registered entrypoints, it doesn't crash
    """
    (pytester.path / "test_one.py").write_text("def test_one(): pass\n")

    def fake_entry_points(group):
        return []

    monkeypatch.setattr(pytest_randomly, "entry_points", fake_entry_points)

    # Need to run in-process so that monkeypatching works
    result = pytester.runpytest_inprocess("--randomly-seed=1")

    assert result.ret == 0


def test_works_without_xdist(simpletestdir):
    out = simpletestdir.runpytest("-p", "no:xdist")
    out.assert_outcomes(passed=1)


@pytest.mark.parametrize("n", list(range(5)))
def test_xdist(n, ourtestdir):
    """
    This test does not expose the original bug (non-shared default seeds) with
    a very high probability, hence multiple runs.
    """
    ourtestdir.makepyfile(
        test_one="def test_a(): pass",
        test_two="def test_a(): pass",
        test_three="def test_a(): pass",
        test_four="def test_a(): pass",
        test_five="def test_a(): pass",
        test_six="def test_a(): pass",
    )

    out = ourtestdir.runpytest("-n", "6", "-v", "--dist=loadfile")
    out.assert_outcomes(passed=6)

    # Can't make any assertion on the order, since output comes back from
    # workers non-deterministically
