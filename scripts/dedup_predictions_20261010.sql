\set ON_ERROR_STOP on
begin;

create temp table _dups on commit drop as
with ranked as (
  select p.id,
         row_number() over (
           partition by p.match_id, p.market
           order by (p.created_at < m.match_date) desc,
                    (exists (select 1 from prediction_results r where r.prediction_id = p.id and r.is_successful is not null)) desc,
                    (split_part(p.id, '-', 2) = to_char(m.match_date at time zone 'America/Bogota', 'YYYYMMDD')) desc,
                    p.created_at desc
         ) as rn
  from predictions p join matches m on m.id = p.match_id
)
select id from ranked where rn > 1;

create table _backup_dup_predictions_20261010 as
  select * from predictions where id in (select id from _dups);
create table _backup_dup_prediction_results_20261010 as
  select * from prediction_results where prediction_id in (select id from _dups);

delete from prediction_progress where prediction_id in (select id from _dups);
delete from prediction_results where prediction_id in (select id from _dups);
delete from predictions where id in (select id from _dups);

select count(*) as remaining_dup_groups from (
  select 1 from predictions group by match_id, market having count(*) > 1
) x;
select (select count(*) from predictions) as predictions_now,
       (select count(*) from _backup_dup_predictions_20261010) as backed_up,
       (select count(*) from _backup_dup_prediction_results_20261010) as backed_up_results;

drop table _backup_match_dates_20261010;
commit;
