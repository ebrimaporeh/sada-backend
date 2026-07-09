from rest_framework.views import APIView
from rest_framework.response import Response
from permissions.base import IsAdminUser
from services.analytics_service import (
    get_dashboard_stats,
    get_donations_by_day,
    get_campaign_status_distribution,
    get_top_campaigns,
    get_top_donors,
    get_recent_donations,
    get_finance_summary,
)


class DashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get aggregated dashboard stats for a date range"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        stats = get_dashboard_stats(start_date, end_date)
        return Response({'success': True, 'data': stats})


class DonationsByDayView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get donations aggregated by day for chart"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        data = get_donations_by_day(start_date, end_date)
        return Response({'success': True, 'data': data})


class CampaignStatusDistributionView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get campaign distribution by status"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        data = get_campaign_status_distribution(start_date, end_date)
        return Response({'success': True, 'data': data})


class TopCampaignsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get top campaigns by amount raised"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = int(request.query_params.get('limit', 5))

        data = get_top_campaigns(start_date, end_date, limit)
        return Response({'success': True, 'data': data})


class TopDonorsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get top donors by total amount"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = int(request.query_params.get('limit', 5))

        data = get_top_donors(start_date, end_date, limit)
        return Response({'success': True, 'data': data})


class RecentDonationsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get recent donations"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = int(request.query_params.get('limit', 10))

        data = get_recent_donations(start_date, end_date, limit)
        return Response({'success': True, 'data': data})


class FinanceSummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get all figures for the admin Finances page, fully aggregated for a period.

        `period` is one of week|month|year|custom (default week). For `custom`,
        `start_date`/`end_date` (YYYY-MM-DD) are required.
        """
        period = request.query_params.get('period')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = int(request.query_params.get('limit', 10))

        data = get_finance_summary(period, start_date, end_date, top_campaigns_limit=limit)
        return Response({'success': True, 'data': data})
