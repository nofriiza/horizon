# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import operator

from django.core.urlresolvers import reverse, reverse_lazy
from django.utils.translation import ugettext_lazy as _

from horizon import api
from horizon import exceptions
from horizon import forms
from horizon import tables
from horizon import usage
from horizon import workflows

from .forms import AddUser
from .tables import TenantsTable, TenantUsersTable, AddUsersTable
from .workflows import CreateProject, UpdateProject

LOG = logging.getLogger(__name__)


QUOTA_FIELDS = ("metadata_items",
                "cores",
                "instances",
                "injected_files",
                "injected_file_content_bytes",
                "volumes",
                "gigabytes",
                "ram",
                "floating_ips")

PROJECT_INFO_FIELDS = ("name",
                       "description",
                       "enabled")


class TenantContextMixin(object):
    def get_object(self):
        if not hasattr(self, "_object"):
            tenant_id = self.kwargs['tenant_id']
            try:
                self._object = api.keystone.tenant_get(self.request,
                                                       tenant_id,
                                                       admin=True)
            except:
                redirect = reverse("horizon:syspanel:projects:index")
                exceptions.handle(self.request,
                                  _('Unable to retrieve project information.'),
                                  redirect=redirect)
        return self._object

    def get_context_data(self, **kwargs):
        context = super(TenantContextMixin, self).get_context_data(**kwargs)
        context['tenant'] = self.get_object()
        return context


class IndexView(tables.DataTableView):
    table_class = TenantsTable
    template_name = 'syspanel/projects/index.html'

    def get_data(self):
        tenants = []
        try:
            tenants = api.keystone.tenant_list(self.request, admin=True)
        except:
            exceptions.handle(self.request,
                              _("Unable to retrieve project list."))
        tenants.sort(key=lambda x: x.id, reverse=True)
        return tenants


class UsersView(tables.MultiTableView):
    table_classes = (TenantUsersTable, AddUsersTable)
    template_name = 'syspanel/projects/users.html'

    def _get_shared_data(self, *args, **kwargs):
        tenant_id = self.kwargs["tenant_id"]
        if not hasattr(self, "_shared_data"):
            try:
                tenant = api.keystone.tenant_get(self.request,
                                                 tenant_id,
                                                 admin=True)
                all_users = api.keystone.user_list(self.request)
                tenant_users = api.keystone.user_list(self.request, tenant_id)
                self._shared_data = {'tenant': tenant,
                                     'all_users': all_users,
                                     'tenant_users': tenant_users}
            except:
                redirect = reverse("horizon:syspanel:projects:index")
                exceptions.handle(self.request,
                                  _("Unable to retrieve users."),
                                  redirect=redirect)
        return self._shared_data

    def get_tenant_users_data(self):
        return self._get_shared_data()["tenant_users"]

    def get_add_users_data(self):
        tenant_users = self._get_shared_data()["tenant_users"]
        all_users = self._get_shared_data()["all_users"]
        tenant_user_ids = [user.id for user in tenant_users]
        return filter(lambda u: u.id not in tenant_user_ids, all_users)

    def get_context_data(self, **kwargs):
        context = super(UsersView, self).get_context_data(**kwargs)
        context['tenant'] = self._get_shared_data()["tenant"]
        return context


class AddUserView(TenantContextMixin, forms.ModalFormView):
    form_class = AddUser
    template_name = 'syspanel/projects/add_user.html'
    success_url = 'horizon:syspanel:projects:users'

    def get_success_url(self):
        return reverse(self.success_url,
                       args=(self.request.POST['tenant_id'],))

    def get_context_data(self, **kwargs):
        context = super(AddUserView, self).get_context_data(**kwargs)
        context['tenant_id'] = self.kwargs["tenant_id"]
        context['user_id'] = self.kwargs["user_id"]
        return context

    def get_form_kwargs(self):
        kwargs = super(AddUserView, self).get_form_kwargs()
        try:
            roles = api.keystone.role_list(self.request)
        except:
            redirect = reverse("horizon:syspanel:projects:users",
                               args=(self.kwargs["tenant_id"],))
            exceptions.handle(self.request,
                              _("Unable to retrieve roles."),
                              redirect=redirect)
        roles.sort(key=operator.attrgetter("id"))
        kwargs['roles'] = roles
        return kwargs

    def get_initial(self):
        default_role = api.keystone.get_default_role(self.request)
        return {'tenant_id': self.kwargs['tenant_id'],
                'user_id': self.kwargs['user_id'],
                'role_id': getattr(default_role, "id", None)}


class TenantUsageView(usage.UsageView):
    table_class = usage.TenantUsageTable
    usage_class = usage.TenantUsage
    template_name = 'syspanel/projects/usage.html'

    def get_data(self):
        super(TenantUsageView, self).get_data()
        return self.usage.get_instances()


class CreateProjectView(workflows.WorkflowView):
    workflow_class = CreateProject
    template_name = "syspanel/projects/create.html"

    def get_initial(self):
        initial = super(CreateProjectView, self).get_initial()

        # get initial quota defaults
        try:
            quota_defaults = api.tenant_quota_defaults(self.request,
                                        self.request.user.tenant_id)
            for field in QUOTA_FIELDS:
                initial[field] = getattr(quota_defaults, field, None)

        except:
            error_msg = _('Unable to retrieve default quota values.')
            self.add_error_to_step(error_msg, 'update_quotas')

        return initial


class UpdateProjectView(workflows.WorkflowView):
    workflow_class = UpdateProject
    template_name = "syspanel/projects/update.html"

    def get_initial(self):
        initial = super(UpdateProjectView, self).get_initial()

        project_id = self.kwargs['tenant_id']
        initial['project_id'] = project_id

        try:
            # get initial project info
            project_info = api.tenant_get(self.request, project_id, admin=True)
            for field in PROJECT_INFO_FIELDS:
                initial[field] = getattr(project_info, field, None)

            # get initial project quota
            quota_data = api.tenant_quota_get(self.request, project_id)
            for field in QUOTA_FIELDS:
                initial[field] = getattr(quota_data, field, None)
        except:
            redirect = reverse("horizon:syspanel:projects:index")
            exceptions.handle(self.request,
                                _('Unable to retrieve project details.'),
                                redirect=redirect)
        return initial
