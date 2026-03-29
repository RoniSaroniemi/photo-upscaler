import {
  pgTable,
  uuid,
  varchar,
  timestamp,
  boolean,
  integer,
  bigint,
  pgEnum,
  index,
  uniqueIndex,
  check,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

// Enums
export const transactionTypeEnum = pgEnum("transaction_type", [
  "deposit",
  "charge",
  "refund",
]);

export const jobStatusEnum = pgEnum("job_status", [
  "pending",
  "processing",
  "completed",
  "failed",
]);

// Users
export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: varchar("email", { length: 255 }).notNull().unique(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

// Magic Link Tokens
export const magicLinkTokens = pgTable(
  "magic_link_tokens",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    email: varchar("email", { length: 255 }).notNull(),
    tokenHash: varchar("token_hash", { length: 255 }).notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    used: boolean("used").notNull().default(false),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("idx_magic_link_token_hash").on(table.tokenHash),
  ]
);

// Balances
export const balances = pgTable(
  "balances",
  {
    userId: uuid("user_id")
      .primaryKey()
      .references(() => users.id),
    amountMicrodollars: bigint("amount_microdollars", { mode: "bigint" })
      .notNull()
      .default(sql`0`),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    check(
      "balance_non_negative",
      sql`${table.amountMicrodollars} >= 0`
    ),
  ]
);

// Transactions
export const transactions = pgTable(
  "transactions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    type: transactionTypeEnum("type").notNull(),
    amountMicrodollars: bigint("amount_microdollars", {
      mode: "bigint",
    }).notNull(),
    stripePaymentIntentId: varchar("stripe_payment_intent_id", {
      length: 255,
    }),
    stripeCheckoutSessionId: varchar("stripe_checkout_session_id", {
      length: 255,
    }),
    jobId: uuid("job_id").references(() => jobs.id),
    description: varchar("description", { length: 500 }),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index("idx_transactions_user_id").on(table.userId),
    index("idx_transactions_job_id").on(table.jobId),
  ]
);

// Jobs
export const jobs = pgTable(
  "jobs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    status: jobStatusEnum("status").notNull().default("pending"),
    inputWidth: integer("input_width"),
    inputHeight: integer("input_height"),
    outputWidth: integer("output_width"),
    outputHeight: integer("output_height"),
    inputFileSize: integer("input_file_size"),
    outputFileSize: integer("output_file_size"),
    processingTimeMs: integer("processing_time_ms"),
    computeCostMicrodollars: bigint("compute_cost_microdollars", {
      mode: "bigint",
    }),
    platformFeeMicrodollars: bigint("platform_fee_microdollars", {
      mode: "bigint",
    }).default(sql`5000`),
    totalCostMicrodollars: bigint("total_cost_microdollars", {
      mode: "bigint",
    }),
    outputGcsKey: varchar("output_gcs_key", { length: 500 }),
    errorMessage: varchar("error_message", { length: 1000 }),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    completedAt: timestamp("completed_at", { withTimezone: true }),
  },
  (table) => [
    index("idx_jobs_user_id").on(table.userId),
    index("idx_jobs_status").on(table.status),
  ]
);

// Free Trial Uses
export const freeTrialUses = pgTable(
  "free_trial_uses",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    ipHash: varchar("ip_hash", { length: 64 }).notNull().unique(),
    usesCount: integer("uses_count").notNull().default(0),
    firstUseAt: timestamp("first_use_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    lastUseAt: timestamp("last_use_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    uniqueIndex("idx_free_trial_ip").on(table.ipHash),
  ]
);
