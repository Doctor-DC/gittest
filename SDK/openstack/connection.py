# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
The :class:`~SDK.openstack.connection.Connection` class is the primary interface
to the Python SDK. It maintains a context for a connection to a region of
a cloud provider. The :class:`~SDK.openstack.connection.Connection` has an
attribute to access each OpenStack service.

At a minimum, the :class:`~SDK.openstack.connection.Connection` class needs to be
created with a config or the parameters to build one.

While the overall system is very flexible, there are four main use cases
for different ways to create a :class:`~SDK.openstack.connection.Connection`.

* Using config settings and keyword arguments as described in
  :ref:`SDK.openstack-config`
* Using only keyword arguments passed to the constructor ignoring config files
  and environment variables.
* Using an existing authenticated `keystoneauth1.session.Session`, such as
  might exist inside of an OpenStack service operational context.
* Using an existing :class:`~SDK.openstack.config.cloud_region.CloudRegion`.

Using config settings
---------------------

For users who want to create a :class:`~SDK.openstack.connection.Connection` making
use of named clouds in ``clouds.yaml`` files, ``OS_`` environment variables
and python keyword arguments, the :func:`SDK.openstack.connect` factory function
is the recommended way to go:

.. code-block:: python

    import SDK.openstack

    conn = SDK.openstack.connect(cloud='example', region_name='earth1')

If the application in question is a command line application that should also
accept command line arguments, an `argparse.Namespace` can be passed to
:func:`SDK.openstack.connect` that will have relevant arguments added to it and
then subsequently consumed by the constructor:

.. code-block:: python

    import argparse
    import SDK.openstack

    options = argparse.ArgumentParser(description='Awesome OpenStack App')
    conn = SDK.openstack.connect(options=options)

Using Only Keyword Arguments
----------------------------

If the application wants to avoid loading any settings from ``clouds.yaml`` or
environment variables, use the :class:`~SDK.openstack.connection.Connection`
constructor directly. As long as the ``cloud`` argument is omitted or ``None``,
the :class:`~SDK.openstack.connection.Connection` constructor will not load
settings from files or the environment.

.. note::

    This is a different default behavior than the :func:`~SDK.openstack.connect`
    factory function. In :func:`~SDK.openstack.connect` if ``cloud`` is omitted
    or ``None``, a default cloud will be loaded, defaulting to the ``envvars``
    cloud if it exists.

.. code-block:: python

    from SDK.openstack import connection

    conn = connection.Connection(
        region_name='example-region',
        auth=dict(
            auth_url='https://auth.example.com',
            username='amazing-user',
            password='super-secret-password',
            project_id='33aa1afc-03fe-43b8-8201-4e0d3b4b8ab5',
            user_domain_id='054abd68-9ad9-418b-96d3-3437bb376703'),
        compute_api_version='2',
        identity_interface='internal')

Per-service settings as needed by `keystoneauth1.adapter.Adapter` such as
``api_version``, ``service_name``, and ``interface`` can be set, as seen
above, by prefixing them with the official ``service-type`` name of the
service. ``region_name`` is a setting for the entire
:class:`~SDK.openstack.config.cloud_region.CloudRegion` and cannot be set per
service.

From existing authenticated Session
-----------------------------------

For applications that already have an authenticated Session, simply passing
it to the :class:`~SDK.openstack.connection.Connection` constructor is all that
is needed:

.. code-block:: python

    from SDK.openstack import connection

    conn = connection.Connection(
        session=session,
        region_name='example-region',
        compute_api_version='2',
        identity_interface='internal')

From existing CloudRegion
-------------------------

If you already have an :class:`~SDK.openstack.config.cloud_region.CloudRegion`
you can pass it in instead:

.. code-block:: python

    from SDK.openstack import connection
    import SDK.openstack.config

    config = SDK.openstack.config.get_cloud_region(
        cloud='example', region_name='earth')
    conn = connection.Connection(config=config)

Using the Connection
--------------------

Services are accessed through an attribute named after the service's official
service-type.

List
~~~~

An iterator containing a list of all the projects is retrieved in this manner:

.. code-block:: python

    projects = conn.identity.projects()

Find or create
~~~~~~~~~~~~~~

If you wanted to make sure you had a network named 'zuul', you would first
try to find it and if that fails, you would create it::

    network = conn.network.find_network("zuul")
    if network is None:
        network = conn.network.create_network(name="zuul")

Additional information about the services can be found in the
:ref:`service-proxies` documentation.
"""
import warnings

import keystoneauth1.exceptions
import requestsexceptions
import six

from SDK.openstack import _log
from SDK.openstack._meta import connection as _meta
from SDK.openstack.cloud import openstackcloud as _cloud
from SDK.openstack import config as _config
from SDK.openstack.config import cloud_region
from SDK.openstack import exceptions
from SDK.openstack import service_description
from SDK.openstack import task_manager as _task_manager

__all__ = [
    'from_config',
    'Connection',
]

if requestsexceptions.SubjectAltNameWarning:
    warnings.filterwarnings(
        'ignore', category=requestsexceptions.SubjectAltNameWarning)

_logger = _log.setup_logging('SDK.openstack')


def from_config(cloud=None, config=None, options=None, **kwargs):
    """Create a Connection using SDK.openstack.config

    :param str cloud:
        Use the `cloud` configuration details when creating the Connection.
    :param SDK.openstack.config.cloud_region.CloudRegion config:
        An existing CloudRegion configuration. If no `config` is provided,
        `SDK.openstack.config.OpenStackConfig` will be called, and the provided
        `name` will be used in determining which cloud's configuration
        details will be used in creation of the `Connection` instance.
    :param argparse.Namespace options:
        Allows direct passing in of options to be added to the cloud config.
        This does not have to be an actual instance of argparse.Namespace,
        despite the naming of the
        `SDK.openstack.config.loader.OpenStackConfig.get_one` argument to which
        it is passed.

    :rtype: :class:`~SDK.openstack.connection.Connection`
    """
    # TODO(mordred) Backwards compat while we transition
    cloud = kwargs.pop('cloud_name', cloud)
    config = kwargs.pop('cloud_config', config)
    if config is None:
        config = _config.OpenStackConfig().get_one(
            cloud=cloud, argparse=options, **kwargs)

    return Connection(config=config)


class Connection(six.with_metaclass(_meta.ConnectionMeta,
                                    _cloud._OpenStackCloudMixin)):

    def __init__(self, cloud=None, config=None, session=None,
                 app_name=None, app_version=None,
                 extra_services=None,
                 strict=False,
                 use_direct_get=False,
                 task_manager=None,
                 rate_limit=None,
                 **kwargs):
        """Create a connection to a cloud.

        A connection needs information about how to connect, how to
        authenticate and how to select the appropriate services to use.

        The recommended way to provide this information is by referencing
        a named cloud config from an existing `clouds.yaml` file. The cloud
        name ``envvars`` may be used to consume a cloud configured via ``OS_``
        environment variables.

        A pre-existing :class:`~SDK.openstack.config.cloud_region.CloudRegion`
        object can be passed in lieu of a cloud name, for cases where the user
        already has a fully formed CloudRegion and just wants to use it.

        Similarly, if for some reason the user already has a
        :class:`~keystoneauth1.session.Session` and wants to use it, it may be
        passed in.

        :param str cloud: Name of the cloud from config to use.
        :param config: CloudRegion object representing the config for the
            region of the cloud in question.
        :type config: :class:`~SDK.openstack.config.cloud_region.CloudRegion`
        :param session: A session object compatible with
            :class:`~keystoneauth1.session.Session`.
        :type session: :class:`~keystoneauth1.session.Session`
        :param str app_name: Name of the application to be added to User Agent.
        :param str app_version: Version of the application to be added to
            User Agent.
        :param extra_services: List of
            :class:`~SDK.openstack.service_description.ServiceDescription`
            objects describing services that openstacksdk otherwise does not
            know about.
        :param bool use_direct_get:
            For get methods, make specific REST calls for server-side
            filtering instead of making list calls and filtering client-side.
            Default false.
        :param task_manager:
            Task Manager to handle the execution of remote REST calls.
            Defaults to None which causes a direct-action Task Manager to be
            used.
        :type manager: :class:`~SDK.openstack.task_manager.TaskManager`
        :param rate_limit:
            Client-side rate limit, expressed in calls per second. The
            parameter can either be a single float, or it can be a dict with
            keys as service-type and values as floats expressing the calls
            per second for that service. Defaults to None, which means no
            rate-limiting is performed.
        :param kwargs: If a config is not provided, the rest of the parameters
            provided are assumed to be arguments to be passed to the
            CloudRegion constructor.
        """
        self.config = config
        self._extra_services = {}
        if extra_services:
            for service in extra_services:
                self._extra_services[service.service_type] = service

        if not self.config:
            if session:
                self.config = cloud_region.from_session(
                    session=session,
                    app_name=app_name, app_version=app_version,
                    load_yaml_config=False,
                    load_envvars=False,
                    **kwargs)
            else:
                self.config = _config.get_cloud_region(
                    cloud=cloud,
                    app_name=app_name, app_version=app_version,
                    load_yaml_config=cloud is not None,
                    load_envvars=cloud is not None,
                    **kwargs)

        if task_manager:
            # If a TaskManager was passed in, don't start it, assume it's
            # under the control of the calling context.
            self.task_manager = task_manager
        else:
            self.task_manager = _task_manager.TaskManager(
                self.config.full_name,
                rate=rate_limit)
            self.task_manager.start()

        self._session = None
        self._proxies = {}
        self.use_direct_get = use_direct_get
        self.strict_mode = strict
        # Call the _OpenStackCloudMixin constructor while we work on
        # integrating things better.
        _cloud._OpenStackCloudMixin.__init__(self)

    @property
    def session(self):
        if not self._session:
            self._session = self.config.get_session()
            # Hide a reference to the connection on the session to help with
            # backwards compatibility for folks trying to just pass
            # conn.session to a Resource method's session argument.
            self.session._sdk_connection = self
        return self._session

    def add_service(self, service):
        """Add a service to the Connection.

        Attaches an instance of the :class:`~SDK.openstack.proxy.Proxy`
        class contained in
        :class:`~SDK.openstack.service_description.ServiceDescription`.
        The :class:`~SDK.openstack.proxy.Proxy` will be attached to the
        `Connection` by its ``service_type`` and by any ``aliases`` that
        may be specified.

        :param SDK.openstack.service_description.ServiceDescription service:
            Object describing the service to be attached. As a convenience,
            if ``service`` is a string it will be treated as a ``service_type``
            and a basic
            :class:`~SDK.openstack.service_description.ServiceDescription`
            will be created.
        """
        # If we don't have a proxy, just instantiate Proxy so that
        # we get an adapter.
        if isinstance(service, six.string_types):
            service = service_description.ServiceDescription(service)
        service_proxy = service._make_proxy(self)

        # Register the proxy class with every known alias
        for attr_name in service.all_types:
            setattr(self, attr_name.replace('-', '_'), service_proxy)

    def authorize(self):
        """Authorize this Connection

        .. note:: This method is optional. When an application makes a call
                  to any OpenStack service, this method allows you to request
                  a token manually before attempting to do anything else.

        :returns: A string token.

        :raises: :class:`~SDK.openstack.exceptions.HttpException` if the
                 authorization fails due to reasons like the credentials
                 provided are unable to be authorized or the `auth_type`
                 argument is missing, etc.
        """
        try:
            return self.session.get_token()
        except keystoneauth1.exceptions.ClientException as e:
            raise exceptions.raise_from_response(e.response)

    def close(self):
        """Release any resources held open."""
        self.task_manager.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
