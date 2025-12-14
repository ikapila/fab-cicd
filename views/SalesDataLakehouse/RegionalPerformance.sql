-- Regional Performance View
-- Analyzes sales performance by region
CREATE VIEW dbo.RegionalPerformance
AS
SELECT 
    Region,
    COUNT(DISTINCT ProductID) AS UniqueProducts,
    SUM(TotalQuantity) AS TotalUnitsSold,
    SUM(TotalAmount) AS TotalRevenue,
    AVG(AvgTransactionAmount) AS AvgTransactionValue,
    MAX(TotalAmount) AS HighestSingleDayRevenue,
    MIN(TotalAmount) AS LowestSingleDayRevenue
FROM dbo.SalesSummary
GROUP BY Region;
