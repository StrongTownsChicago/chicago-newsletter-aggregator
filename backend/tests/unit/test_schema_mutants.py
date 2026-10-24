"""Unit tests for tools/schema_mutants.py."""

import unittest
from dataclasses import replace

from tools.schema_mutants import (
    ColumnDefault,
    Constraint,
    Function,
    Policy,
    SchemaCatalog,
    SchemaMutant,
    TableName,
    Trigger,
    UniqueIndex,
    generate_mutants,
    operator_variants,
    swap_foreign_key_action,
)

RULES = TableName("public", "notification_rules")
REPORTS = TableName("public", "weekly_topic_reports")


def labels(mutants: list[SchemaMutant]) -> list[str]:
    return [mutant.label for mutant in mutants]


OWN_ROWS_POLICY = Policy(
    RULES,
    "Users can view own rules",
    "SELECT",
    ("public",),
    permissive=True,
    using="(auth.uid() = user_id)",
    check=None,
)


class TestPolicyMutants(unittest.TestCase):
    def test_owner_policy_is_dropped_and_loosened_and_restored_as_it_was(self) -> None:
        dropped, loosened = generate_mutants(SchemaCatalog(policies=(OWN_ROWS_POLICY,)))

        drop = 'DROP POLICY "Users can view own rules" ON "public"."notification_rules"'
        create = (
            'CREATE POLICY "Users can view own rules" ON "public"."notification_rules"'
            " AS PERMISSIVE FOR SELECT TO PUBLIC USING ((auth.uid() = user_id))"
        )
        self.assertEqual(dropped.apply, (drop,))
        self.assertEqual(
            loosened.apply, (drop, create.replace("(auth.uid() = user_id)", "true"))
        )
        restore = (drop.replace("DROP POLICY", "DROP POLICY IF EXISTS"), create)
        self.assertEqual(dropped.restore, restore)
        self.assertEqual(loosened.restore, restore)

    def test_skips_mutants_that_cannot_change_behaviour(self) -> None:
        block_inserts = replace(
            OWN_ROWS_POLICY,
            name="Block inserts",
            command="INSERT",
            using=None,
            check="false",
        )
        public_read = replace(OWN_ROWS_POLICY, name="Public read", using="true")
        service_only = replace(
            OWN_ROWS_POLICY,
            table=REPORTS,
            name="Service",
            roles=("service_role",),
            command="ALL",
        )

        mutants = generate_mutants(
            SchemaCatalog(policies=(block_inserts, public_read, service_only))
        )

        self.assertEqual(
            labels(mutants),
            [
                "notification_rules policy 'Block inserts': condition replaced with true",
                "notification_rules policy 'Public read': dropped",
                "weekly_topic_reports policy 'Service': applies to every role",
            ],
        )
        self.assertIn("WITH CHECK (true)", mutants[0].apply[1])
        self.assertIn("TO PUBLIC", mutants[2].apply[1])


class TestConstraintMutants(unittest.TestCase):
    def test_check_is_dropped_and_its_operators_mutated(self) -> None:
        check = Constraint(
            RULES, "search_term_check", "c", "CHECK ((length(search_term) <= 100))"
        )

        mutants = generate_mutants(SchemaCatalog(constraints=(check,)))

        drop = 'ALTER TABLE "public"."notification_rules" DROP CONSTRAINT "search_term_check"'
        add = 'ALTER TABLE "public"."notification_rules" ADD CONSTRAINT "search_term_check" '
        self.assertEqual(
            [mutant.apply for mutant in mutants],
            [
                (drop,),
                (drop, add + "CHECK ((length(search_term) < 100))"),
                (drop, add + "CHECK ((length(search_term) <= 101))"),
            ],
        )
        for mutant in mutants:
            self.assertEqual(
                mutant.restore,
                (
                    drop.replace("CONSTRAINT", "CONSTRAINT IF EXISTS"),
                    add + check.definition,
                ),
            )

    def test_foreign_key_on_delete_action_is_swapped(self) -> None:
        references = "FOREIGN KEY (user_id) REFERENCES auth.users(id)"
        for definition, mutated in (
            (f"{references} ON DELETE CASCADE", f"{references} ON DELETE NO ACTION"),
            (f"{references} ON DELETE SET NULL", f"{references} ON DELETE CASCADE"),
            (references, f"{references} ON DELETE CASCADE"),
        ):
            with self.subTest(definition=definition):
                self.assertEqual(swap_foreign_key_action(definition)[0], mutated)

    def test_unique_constraint_and_index_are_dropped(self) -> None:
        index_sql = "CREATE UNIQUE INDEX idx ON public.weekly_topic_reports (topic)"
        mutants = generate_mutants(
            SchemaCatalog(
                constraints=(
                    Constraint(
                        REPORTS, "unique_topic_week", "u", "UNIQUE (topic, week_id)"
                    ),
                ),
                unique_indexes=(UniqueIndex(REPORTS, "idx", index_sql),),
            )
        )

        self.assertEqual([mutant.kind for mutant in mutants], ["unique", "unique"])
        self.assertEqual(mutants[1].apply, ('DROP INDEX "public"."idx"',))
        self.assertEqual(
            mutants[1].restore, ('DROP INDEX IF EXISTS "public"."idx"', index_sql)
        )


class TestOtherMutants(unittest.TestCase):
    def test_rls_defaults_and_triggers(self) -> None:
        trigger_sql = "CREATE TRIGGER t AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION f()"
        mutants = generate_mutants(
            SchemaCatalog(
                rls_tables=(RULES,),
                column_defaults=(
                    ColumnDefault(RULES, "is_active", "true"),
                    ColumnDefault(RULES, "id", "gen_random_uuid()"),
                ),
                triggers=(Trigger(TableName("auth", "users"), "t", trigger_sql),),
            )
        )

        self.assertEqual(
            [(mutant.kind, mutant.apply) for mutant in mutants],
            [
                (
                    "rls",
                    (
                        'ALTER TABLE "public"."notification_rules" DISABLE ROW LEVEL SECURITY',
                    ),
                ),
                (
                    "default",
                    (
                        'ALTER TABLE "public"."notification_rules" ALTER COLUMN "is_active" DROP DEFAULT',
                    ),
                ),
                ("trigger", ('DROP TRIGGER "t" ON "auth"."users"',)),
            ],
        )
        self.assertEqual(mutants[2].restore[1], trigger_sql)

    def test_function_body_operators_and_security_definer_are_mutated(self) -> None:
        definition = (
            "CREATE OR REPLACE FUNCTION public.f(n integer)\n RETURNS integer\n"
            " LANGUAGE sql\n SECURITY DEFINER\nAS $function$\n"
            "SELECT count(*) FROM t WHERE a = n -- a = b\n$function$\n"
        )

        mutants = generate_mutants(
            SchemaCatalog(functions=(Function("f(integer)", definition),))
        )

        self.assertEqual(
            labels(mutants),
            ["f(integer): SECURITY DEFINER -> INVOKER", "f(integer): = -> <> (line 2)"],
        )
        self.assertNotIn("SECURITY DEFINER", mutants[0].apply[0])
        self.assertIn("WHERE a <> n -- a = b", mutants[1].apply[0])
        self.assertTrue(all(mutant.restore == (definition,) for mutant in mutants))


class TestOperatorVariants(unittest.TestCase):
    def test_leaves_literals_identifiers_comments_and_assignments_alone(self) -> None:
        sql = "x := 'a = b' || \"c<d\"; -- e > f\n/* g AND h */ y => z"

        self.assertEqual(operator_variants(sql), [])

    def test_each_variant_changes_one_token(self) -> None:
        self.assertEqual(
            operator_variants("a >= 1 AND b IS NULL"),
            [
                (">= -> > (line 1)", "a > 1 AND b IS NULL"),
                ("AND -> OR (line 1)", "a >= 1 OR b IS NULL"),
                ("IS NULL -> IS NOT NULL (line 1)", "a >= 1 AND b IS NOT NULL"),
                ("n -> n+1 (line 1)", "a >= 2 AND b IS NULL"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
