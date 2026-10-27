-- Extensions and schemas that every later migration builds on.
-- Roles, grants and row-level security arrive in Phase 1.

create extension if not exists vector;

create schema if not exists raw;
create schema if not exists staging;
create schema if not exists intermediate;
create schema if not exists marts;
create schema if not exists retrieval;
create schema if not exists ops;
create schema if not exists evals;
create schema if not exists docflow;
