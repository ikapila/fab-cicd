-- ----------------------------------------------------------
-- View: vw_aggregated_odessa_fact_asset_status_latest
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_aggregated_odessa_fact_asset_status_latest AS
with asset_fact_order as (
SELECT asset.bk_aggregated_dim_asset_id, fstatus.*,
ROW_NUMBER() OVER(PARTITION BY asset.bk_aggregated_dim_asset_id ORDER BY asset.sk_aggregated_dim_asset DESC) AS fact_asset_status_order
FROM aggregated_odessa_dim_asset asset
LEFT JOIN aggregated_odessa_fact_asset_status fstatus ON fstatus.sk_aggregated_dim_asset = asset.sk_aggregated_dim_asset
WHERE fstatus.sk_aggregated_dim_asset IS NOT NULL 
)
select bk_aggregated_dim_asset_id,
sk_aggregated_dim_asset,
sk_aggregated_dim_legal_entity,
sk_aggregated_dim_date_record,
sk_aggregated_dim_time_record,
sk_aggregated_dim_asset_status,
sk_aggregated_dim_asset_type,
sk_aggregated_dim_currency,
sk_aggregated_dim_vehicle_detail,
dealer_cost_amount,
residual_amount,
salvage_amount,
base_price_of_equipment_amount,
quantity,
dp_process_datetime,
dp_process_date,
dp_record_insert_datetime,
dp_process_name,
dp_source_name 
from asset_fact_order 
where fact_asset_status_order = 1;
GO
-- ----------------------------------------------------------
-- View: vw_asset
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset
AS
SELECT * FROM dbo.table_vw_asset;
GO
-- ----------------------------------------------------------
-- View: vw_asset_value
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_asset_value AS

WITH initial_avh AS (
SELECT
	*,
	ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY income_date ASC, [bk_aggregated_dim_asset_value_history_id] ASC) AS InitialRowNo
FROM aggregated_odessa_dim_asset_value_history
WHERE
	is_lessor_owned = 1
	AND is_schedule = 1
	AND is_accounted = 1
	AND is_cleared = 1
	AND income_date <= GETDATE()
),
current_avh AS (
SELECT
	*,
	ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY income_date DESC, bk_aggregated_dim_asset_value_history_id DESC) AS CurrentRowNo

FROM aggregated_odessa_dim_asset_value_history
WHERE
	is_lessor_owned = 1
	AND is_schedule = 1
	AND is_accounted = 1
    AND gl_journal_id IS NOT NULL
	AND income_date <= GETDATE()
   AND current_flag = 1

)

SELECT
bk_aggregated_dim_asset_id AS asset_id,
bbv.begin_book_value_amount,
bbv.cost_amount,
ebv.end_book_value_amount
FROM aggregated_odessa_dim_asset AS asset
LEFT JOIN initial_avh AS bbv ON asset.bk_aggregated_dim_asset_id = bbv.asset_id AND bbv.InitialRowNo = 1
LEFT JOIN current_avh AS ebv ON asset.bk_aggregated_dim_asset_id = ebv.asset_id AND ebv.CurrentRowNo = 1



WHERE asset.current_flag = 1 

;
GO
-- ----------------------------------------------------------
-- View: vw_book_depreciation
-- ----------------------------------------------------------
CREATE OR ALTER VIEW vw_book_depreciation
AS
SELECT *
FROM
( 
	SELECT      [bk_aggregated_dim_book_depreciation_id],
				[sk_aggregated_dim_book_depreciation],
				[cost_basis_amount],
				[salvage_amount],
				[scrap_amount],
				[cost_center_id],
				[book_depreciation_template_id],
				[asset_id],
				[contract_id],
				[last_amort_run_date],
				[reversal_post_date],
				[remaining_life_in_months],
				[per_day_depreciation_factor],
				[begin_date],
				[terminated_date],
				[is_active],
				current_flag,				
				ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY ISNULL(terminated_date, end_date) DESC, begin_date DESC) AS current_asset_value,
				ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY ISNULL(contract_id, -1) DESC, begin_date DESC, sk_aggregated_dim_book_depreciation DESC) AS current_contract_value,	
				ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY begin_date ASC) AS initial_asset_value,
				ROW_NUMBER() OVER(PARTITION BY asset_id, contract_id ORDER BY begin_date ASC) AS initial_contract_value							
	FROM aggregated_odessa_dim_book_depreciation
	WHERE current_flag = 1 
	AND is_active = 1
) AS a

;
GO
